import asyncio
import enum
import html
import io
import typing
import xml.etree
import xml.etree.ElementTree
from urllib.parse import urlparse, urlunparse
from xml.sax.saxutils import escape

import async_upnp_client
from aiohttp.web_request import Request
from aiohttp.web_response import Response
from async_upnp_client.aiohttp import AiohttpRequester
from async_upnp_client.client import UpnpService, UpnpDevice as UpnpServiceDevice
from async_upnp_client.client_factory import UpnpFactory
from async_upnp_client.event_handler import UpnpEventHandler
from async_upnp_client.exceptions import UpnpError
from async_upnp_client.search import async_search

from ..device import Device, DeviceFinder, RoutersDefType, RequestHandler

__all__ = ["Finder"]


_AVTRANSPORT_SCHEMA = "urn:schemas-upnp-org:service:AVTransport:1"

_VIDEO_FLAGS = "21700000000000000000000000000000"

_DLL_METADATA = """
<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/"
    xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/"
    xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/"
    xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">
    <item id="R:0/0/0" parentID="R:0/0" restricted="true">
        <dc:title>{title}</dc:title>
        <upnp:class>object.item.videoItem.movie</upnp:class>
        <desc id="cdudn" nameSpace="urn:schemas-rinconnetworks-com:metadata-1-0/">
            SA_RINCON65031_
        </desc>
        <res protocolInfo="http-get:*:video/mp4:DLNA.ORG_OP=01;DLNA.ORG_CI=0;DLNA.ORG_FLAGS={flags}">{url}</res>
    </item>
</DIDL-Lite>
"""

_STATUS_TAG = "{urn:schemas-upnp-org:metadata-1-0/AVT/}TransportStatus"


def ascii_only(haystack: str) -> str:
    return "".join(c for c in haystack if ord(c) < 128)


def base_url(host, port) -> str:
    return f"http://{host}:{port}"


async def _upnp_safe_stop(service: UpnpService):
    stop = service.action("Stop")

    try:
        await stop.async_call(InstanceID=0)
    except UpnpError as error:
        normalized_error = str(error).lower()

        if "transition not available" in normalized_error:
            return

        if "action stop failed" in normalized_error:
            return

        raise error


class UpnpPlayerStatus(enum.Enum):
    PLAYING = enum.auto()
    ERROR = enum.auto()
    NOTHING = enum.auto()
    STOPPED = enum.auto()


def _player_status(data: bytes) -> UpnpPlayerStatus:
    event: xml.etree.ElementTree.Element
    decoded = html.unescape(data.decode("utf8"))

    stream = io.StringIO()
    stream.write(decoded)
    stream.seek(0)

    parser = xml.etree.ElementTree.iterparse(stream)
    reach_ok = False

    for _, event in parser:
        if event.tag == _STATUS_TAG:
            status = event.get("val")

            if status == "OK":
                reach_ok = True

            if status == "STOPPED":
                return UpnpPlayerStatus.STOPPED

            if status == "ERROR_OCCURRED":
                return UpnpPlayerStatus.ERROR

    if reach_ok:
        return UpnpPlayerStatus.PLAYING

    return UpnpPlayerStatus.NOTHING


class DeviceStatus:
    def __init__(self, device: "UpnpDevice", playing: bool = False, errored: bool = False):
        self.device = device
        self.playing = playing
        self.errored = errored


class UpnpNotifyServer(RequestHandler):
    _devices: typing.Dict[int, DeviceStatus]

    def __init__(self):
        self._devices = {}

    def add_device(self, device: DeviceStatus, local_token: int):
        self._devices[local_token] = device

    def remove_device(self, local_token: int):
        if local_token in self._devices:
            del self._devices[local_token]

    def get_path(self) -> str:
        return "/upnp/notify/{local_token}"

    def get_method(self) -> str:
        return "NOTIFY"

    async def handle(self, request: Request) -> Response:
        local_token_raw: str = request.match_info["local_token"]

        if not local_token_raw.isdigit():
            return Response(status=400)

        local_token: int = int(local_token_raw)

        if local_token not in self._devices:
            return Response(status=403)

        device = self._devices[local_token]
        data = await request.read()
        status = _player_status(data)

        if status == UpnpPlayerStatus.PLAYING:
            device.playing = True

        if status == UpnpPlayerStatus.ERROR and device.playing:
            device.errored = True

        if device.errored and status == UpnpPlayerStatus.NOTHING:
            device.errored = False
            device.playing = False
            await device.device.reconnect()

        return Response(status=200)


class NotifyServer(async_upnp_client.event_handler.UpnpNotifyServer):
    def __init__(self, url):
        super().__init__()
        self.url = url

    @property
    def callback_url(self) -> str:
        return self.url

    async def async_start_server(self) -> None:
        pass

    async def async_stop_server(self) -> None:
        pass


class SubscribeTask:
    _service: UpnpService
    _task: typing.Optional[asyncio.Task]
    _event_handler: UpnpEventHandler

    def __init__(self,
                 device: UpnpServiceDevice,
                 service: UpnpService,
                 url: str):
        self._service = service
        self._task = None
        self._event_handler = UpnpEventHandler(NotifyServer(url), device.requester)

    async def start(self):
        await self.close()
        self._task = asyncio.create_task(self._loop())

    async def close(self):
        task = self._task
        self._task = None

        if task is not None:
            task.cancel()
            await self._event_handler.async_unsubscribe_all()

    async def _loop(self):
        await self._event_handler.async_subscribe(self._service)

        while True:
            await asyncio.sleep(10)
            # async_resubscribe_all NOT WORK ON SAMSUNG TV
            await self._event_handler.async_unsubscribe_all()
            await self._event_handler.async_subscribe(self._service)


class UpnpDevice(Device):
    _device: UpnpServiceDevice
    _service: UpnpService
    _subscribe_task: typing.Optional[SubscribeTask]
    _notify_handler: UpnpNotifyServer

    def __init__(self, device: UpnpServiceDevice, notify_handler: UpnpNotifyServer):
        self._device = device
        self._service = self._device.service(_AVTRANSPORT_SCHEMA)
        self._notify_handler = notify_handler
        self._subscribe_task = None

    def get_device_name(self) -> str:
        return self._device.friendly_name

    async def stop(self):
        await _upnp_safe_stop(self._service)

    async def on_close(self, local_token: int):
        task = self._subscribe_task

        if task is not None:
            await task.close()

        self._notify_handler.remove_device(local_token)

    async def play(self, url: str, title: str, local_token: int):
        set_url = self._service.action("SetAVTransportURI")
        meta = _DLL_METADATA.format(title=escape(ascii_only(title)), url=escape(url), flags=_VIDEO_FLAGS)
        await set_url.async_call(InstanceID=0, CurrentURI=url, CurrentURIMetaData=meta)

        device_status = DeviceStatus(self)
        self._notify_handler.add_device(device_status, local_token)

        subscribe_url = urlunparse(urlparse(url)._replace(path=f"/upnp/notify/{local_token}"))
        self._subscribe_task = SubscribeTask(self._device, self._service, subscribe_url)
        await self._subscribe_task.start()

        play = self._service.action("Play")
        await play.async_call(InstanceID=0, Speed="1")

    async def resume(self):
        play = self._service.action("Play")
        await play.async_call(InstanceID=0, Speed="1")

    async def pause(self):
        play = self._service.action("Pause")
        await play.async_call(InstanceID=0)

    async def reconnect(self):
        play = self._service.action("Play")
        await play.async_call(InstanceID=0, Speed="1")


class UpnpDeviceFinder(DeviceFinder):
    singleton = True

    def __init__(self, config):
        super().__init__(config)
        self._notify_handler = UpnpNotifyServer()

    async def find(self) -> typing.List[Device]:
        devices = []
        requester = AiohttpRequester()
        factory = UpnpFactory(requester)
        found_locations = set()

        async def on_response(data: typing.Mapping[str, typing.Any]) -> None:
            location = data.get("LOCATION")
            if location not in found_locations:
                found_locations.add(location)
                devices.append(await factory.async_create_device(location))

        await async_search(search_target=_AVTRANSPORT_SCHEMA,
                           timeout=self.request_timeout,
                           async_callback=on_response)

        return [UpnpDevice(device, self._notify_handler) for device in devices]

    def get_routers(self) -> RoutersDefType:
        return [self._notify_handler]


Finder = UpnpDeviceFinder
