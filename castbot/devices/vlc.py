import asyncio
import logging
import re
import typing

from ..utils import DeviceControlError, LocalToken
from ..device import DeviceFinder, Device, PlaybackStatus

__all__ = ["Finder"]

_LOGGER = logging.getLogger(__name__)
_ENCODING = "utf8"
_EOF = b"\n\r"
_AUTH_MAGIC = b"\xff\xfb\x01"
_AUTH_OK = b"\xff\xfc\x01\r\nWelcome"
_AUTH_PROMPT = b"Password: " + _AUTH_MAGIC
_HANDSHAKE_TIMEOUT = 5
_STATUS_LINE = re.compile(r"\( state (\w+) \)")
_INPUT_LINE = re.compile(r"\( new input: (.*) \)")


async def _read_prefix(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, expected: bytes) -> bytes:
    reply = bytearray()
    try:
        async with asyncio.timeout(_HANDSHAKE_TIMEOUT):
            while len(reply) < len(expected) and expected.startswith(reply):
                chunk = await reader.read(len(expected) - len(reply))
                if not chunk:
                    raise ConnectionError("VLC closed the connection during the handshake")
                reply.extend(chunk)
    except (Exception, asyncio.CancelledError):
        writer.close()
        raise
    return bytes(reply)


async def _read_status(reader: asyncio.StreamReader) -> tuple[str, str | None]:
    url = None
    async with asyncio.timeout(_HANDSHAKE_TIMEOUT):
        while line := await reader.readline():
            text = line.decode(_ENCODING, errors="replace")
            if item := _INPUT_LINE.search(text):
                url = item[1]
            if status := _STATUS_LINE.search(text):
                return status[1], url
    raise DeviceControlError("VLC did not report playback status")


class VlcDeviceParams:
    _host: str
    _port: int
    _password: typing.Optional[str] = None

    def __init__(self, params: typing.Dict[str, typing.Any]):
        self._host = params["host"]
        self._port = params["port"]

        if "password" in params:
            self._password = params["password"]

    @property
    def host(self) -> str:
        return self._host

    @property
    def port(self) -> int:
        return self._port

    @property
    def password(self) -> typing.Optional[str]:
        return self._password


class VlcDevice(Device):
    params: VlcDeviceParams

    def __init__(self, device: VlcDeviceParams):
        self._params = device

    def get_device_name(self) -> str:
        return f"vlc @{self._params.host}"

    def get_device_key(self) -> str:
        return f"{self._params.host}:{self._params.port}"

    async def _call(self, method: str, *args: str, read_status: bool = False):
        reader, writer = await asyncio.open_connection(self._params.host, self._params.port)
        headers = await _read_prefix(reader, writer, _AUTH_PROMPT)

        if headers.endswith(_AUTH_MAGIC):
            if self._params.password:
                writer.write(bytes(self._params.password, _ENCODING) + _EOF)
                await writer.drain()

                auth_result = await _read_prefix(reader, writer, _AUTH_OK)

                if not auth_result.startswith(_AUTH_OK):
                    _LOGGER.error("VLC rejected authentication")
                    writer.close()
                    raise DeviceControlError("VLC rejected authentication")

            else:
                _LOGGER.error("vlc %s: need password", self._params.host)
                writer.close()
                raise DeviceControlError("VLC requires a password")

        try:
            writer.write(method.encode(_ENCODING) + b" " + b" ".join(a.encode(_ENCODING) for a in args) + _EOF)
            await writer.drain()
            return await _read_status(reader) if read_status else None
        finally:
            writer.close()

    async def stop(self):
        await self._call("stop")

    async def on_close(self, local_token: LocalToken):
        pass

    async def play(self, url: str, title: str, local_token: LocalToken, *, content_type: str = "video/mp4"):
        await self._call("add", url)
        await self._call("play")

    async def play_playlist_item(self, url: str, title: str, local_token: LocalToken):
        await self._call("clear")
        await self._call("repeat", "off")
        await self._call("loop", "off")
        await self.play(url, title, local_token)

    async def playlist_status(self, url: str) -> PlaybackStatus:
        state, current_url = await self._call("status", read_status=True)
        if current_url and current_url != url:
            return PlaybackStatus.INTERRUPTED
        if state in {"playing", "paused"}:
            return PlaybackStatus.ACTIVE
        if state == "stopped":
            return PlaybackStatus.IDLE
        return PlaybackStatus.BUFFERING


class VlcDeviceFinder(DeviceFinder):
    def __init__(self, config):
        super().__init__(config)
        self._device_config = config

    async def find(self) -> typing.List[Device]:
        return [VlcDevice(VlcDeviceParams(self._device_config))]


Finder = VlcDeviceFinder
