import abc
import typing

from aiohttp.web_request import Request
from aiohttp.web_response import Response

from castbot.utils import ConfigError


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
]


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
    def on_close(self, local_token: int):
        raise NotImplementedError

    def __repr__(self):
        return self.get_device_name()


class DeviceFinder(abc.ABC):
    singleton = False
    device_finder = {}

    def __init__(self, config):
        self.request_timeout = int(config.get("request_timeout", 5))
        if self.singleton:
            cls = self.__class__
            if cls.__name__ not in self.device_finder:
                self.device_finder[cls.__name__] = self
            else:
                raise ConfigError("Multiple chromecast devices specified in config")

    @abc.abstractmethod
    async def find(self) -> typing.List[Device]:
        raise NotImplementedError

    def get_routers(self) -> RoutersDefType:
        return []
