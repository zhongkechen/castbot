import asyncio
import io
import logging
import typing

from ..utils import LocalToken
from ..device import DeviceFinder, Device

__all__ = ["Finder"]

_LOGGER = logging.getLogger(__name__)
_ENCODING = "utf8"
_EOF = b"\n\r"
_AUTH_MAGIC = b"\xff\xfb\x01"
_AUTH_OK = b"\xff\xfc\x01\r\nWelcome"


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

    async def _call(self, method: str, *args: typing.AnyStr):
        reader, writer = await asyncio.open_connection(self._params.host, self._params.port)
        headers = await reader.read(io.DEFAULT_BUFFER_SIZE)

        if headers.endswith(_AUTH_MAGIC):
            if self._params.password:
                writer.write(bytes(self._params.password, _ENCODING) + _EOF)
                await writer.drain()

                auth_result = await reader.read(io.DEFAULT_BUFFER_SIZE)

                if not auth_result.startswith(_AUTH_OK):
                    _LOGGER.error("receive: %s", auth_result.decode(_ENCODING, "ignore"))
                    return writer.close()

            else:
                _LOGGER.error("vlc %s: need password", self._params.host)
                return writer.close()

        writer.write(method.encode(_ENCODING) + b" " + b" ".join(a.encode(_ENCODING) for a in args) + _EOF)

        await writer.drain()
        return writer.close()

    async def stop(self):
        await self._call("stop")

    async def on_close(self, local_token: LocalToken):
        pass

    async def play(self, url: str, title: str, local_token: LocalToken):
        await self._call("add", url)
        await self._call("play")


class VlcDeviceFinder(DeviceFinder):
    def __init__(self, config):
        super().__init__(config)
        self._device_config = config

    async def find(self) -> typing.List[Device]:
        return [VlcDevice(VlcDeviceParams(self._device_config))]


Finder = VlcDeviceFinder
