import abc
import typing

from aiohttp.web_request import Request
from aiohttp.web_response import Response


class RequestHandler(abc.ABC):
    @abc.abstractmethod
    def get_path(self) -> str:
        raise NotImplementedError

    @abc.abstractmethod
    async def handle(self, request: Request) -> Response:
        raise NotImplementedError

    @abc.abstractmethod
    def get_method(self) -> str:
        raise NotImplementedError


RoutersDefType = typing.List[RequestHandler]

__all__ = [
    "Device",
    "DeviceFinder",
    "RoutersDefType",
    "RequestHandler",
    "DevicePlayerFunction"
]


class DevicePlayerFunction(abc.ABC):
    @abc.abstractmethod
    async def get_name(self) -> str:
        raise NotImplementedError

    @abc.abstractmethod
    async def handle(self):
        raise NotImplementedError


class Device(abc.ABC):
    @abc.abstractmethod
    async def stop(self):
        raise NotImplementedError

    @abc.abstractmethod
    async def play(self, url: str, title: str, local_token: int):
        raise NotImplementedError

    @abc.abstractmethod
    def get_device_name(self) -> str:
        raise NotImplementedError

    @abc.abstractmethod
    def get_player_functions(self) -> typing.List[DevicePlayerFunction]:
        raise NotImplementedError

    @abc.abstractmethod
    def on_close(self, local_token: int):
        raise NotImplementedError

    def __repr__(self):
        return self.get_device_name()


class DeviceFinder(abc.ABC):
    @abc.abstractmethod
    async def find(self) -> typing.List[Device]:
        raise NotImplementedError

    def get_routers(self) -> RoutersDefType:
        return []
