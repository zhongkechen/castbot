import time
import typing

from aiohttp.web_request import Request
from aiohttp.web_response import Response

from ..device import DeviceFinder, RoutersDefType, Device, RequestHandler
from ..utils import secret_token, LocalToken

__all__ = ["Finder"]


class WebDevice(Device):
    _url_to_play: typing.Optional[str] = None
    _device_name: str
    _remote_token: int
    _devices: typing.Dict[int, "WebDevice"]
    _manipulation_timestamp: float

    def __init__(self, device_name: str, token: int, devices: typing.Dict[int, "WebDevice"]):
        self._device_name = device_name
        self._remote_token = token
        self._devices = devices
        self._manipulation_timestamp = time.time()

    async def stop(self):
        self._url_to_play = None

    async def on_close(self, local_token: LocalToken):
        self._devices.pop(self._remote_token, None)

    async def play(self, url: str, title: str, local_token: LocalToken):
        self._url_to_play = url

    def manipulate_timestamp(self) -> float:
        old = self._manipulation_timestamp
        self._manipulation_timestamp = time.time()
        return old

    def get_token(self) -> int:
        return self._remote_token

    def get_device_name(self) -> str:
        return self._device_name

    def get_url_to_play(self) -> typing.Optional[str]:
        tmp = self._url_to_play
        self._url_to_play = None
        return tmp


class WebDeviceApiRequestRegisterDevice(RequestHandler):
    _devices: typing.Dict[int, WebDevice]

    def __init__(self, password: str, devices: typing.Dict[int, WebDevice]):
        self._devices = devices
        self._password = password

    def get_path(self) -> str:
        return "/web/api/register/{password}"

    def get_method(self) -> str:
        return "GET"

    async def handle(self, request: Request) -> Response:
        password = request.match_info["password"]

        if password != self._password:
            return Response(status=403)

        remote_token = secret_token()
        self._devices[remote_token] = WebDevice(f"web @({request.remote})", remote_token, self._devices)
        return Response(status=200, body=str(remote_token))


class WebDeviceApiRequestPoll(RequestHandler):
    _devices: typing.Dict[int, WebDevice]

    def __init__(self, devices: typing.Dict[int, WebDevice]):
        self._devices = devices

    def get_path(self) -> str:
        return "/web/api/poll/{remote_token}"

    def get_method(self) -> str:
        return "GET"

    async def handle(self, request: Request) -> Response:
        try:
            remote_token = int(request.match_info["remote_token"])
        except ValueError:
            return Response(status=400)

        try:
            device = self._devices[remote_token]
        except KeyError:
            return Response(status=404)

        device.manipulate_timestamp()
        url_to_play = device.get_url_to_play()

        if url_to_play is None:
            return Response(status=302)

        return Response(status=200, body=url_to_play)


class WebDeviceFinder(DeviceFinder):
    def __init__(self, config):
        super().__init__(config)
        self._devices = {}
        self._password = str(config.get("password", ""))

    async def find(self) -> typing.List[Device]:
        devices = list(self._devices.values())
        min_timestamp = time.time() - self.request_timeout

        for device in devices:
            if device.manipulate_timestamp() < min_timestamp:
                self._devices.pop(device.get_token(), None)

        return list(self._devices.values())

    def get_routers(self) -> RoutersDefType:
        return [
            WebDeviceApiRequestRegisterDevice(self._password, self._devices),
            WebDeviceApiRequestPoll(self._devices),
        ]


Finder = WebDeviceFinder
