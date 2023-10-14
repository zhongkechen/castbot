import abc
import asyncio
import importlib
import logging
import os.path
import pkgutil
import typing

import async_timeout
from aiohttp.web_request import Request
from aiohttp.web_response import Response

from castbot import devices
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
    device_finder: typing.Set["DeviceFinder"] = set()

    def __init__(self, config):
        self.config = config
        self.request_timeout = int(config.get("request_timeout", 5))
        if self not in self.device_finder:
            logging.info("DeviceFinder added: %s", config)
            self.device_finder.add(self)
        else:
            logging.error("Duplicate DeviceFinder config: %s", config)
            raise ConfigError("Multiple same devices specified in config")

    def __hash__(self):
        return hash(tuple(sorted(self.config.items())))

    def __eq__(self, other):
        if self is other:
            return True
        if isinstance(other, DeviceFinder):
            return other.config == self.config
        return False

    @abc.abstractmethod
    async def find(self) -> typing.List[Device]:
        raise NotImplementedError

    def get_routers(self) -> RoutersDefType:
        return []


class DeviceFinderCollection:
    def __init__(self, config):
        self._finder_classes: typing.Dict[str, DeviceFinder.__class__] = {
            name: importlib.import_module("." + name, "castbot.devices").Finder
            for _, name, _ in pkgutil.iter_modules([os.path.dirname(devices.__file__)])}
        self._finders = [self._finder_classes[device_config["type"]](device_config) for device_config in config]
        self._devices: typing.List[Device] = []

    def get_all_routers(self):
        for finder in self._finders:
            routers = finder.get_routers()

            for handler in routers:
                yield handler.get_method(), handler.get_path(), handler.handle

    @staticmethod
    async def _refresh_one_finder(finder):
        try:
            with async_timeout.timeout(finder.request_timeout + 1):
                return await finder.find()
        except asyncio.CancelledError:
            pass

    async def refresh_all_devices(self):
        find_devices = [self._refresh_one_finder(finder) for finder in self._finders]
        found_devices = await asyncio.gather(*find_devices)
        self._devices = [d for found_device in found_devices for d in found_device if d]

    async def find_device_by_name(self, device_name):
        if not self._devices:
            await self.refresh_all_devices()
        found_devices = [d for d in self._devices if repr(d) == device_name]
        return found_devices[0] if found_devices else None

    async def list_all_devices(self):
        if not self._devices:
            await self.refresh_all_devices()
        return self._devices


__all__ = [
    "Device",
    "DeviceFinder",
    "RoutersDefType",
    "RequestHandler",
    "DeviceFinderCollection"
]
