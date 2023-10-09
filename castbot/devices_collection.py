import asyncio
import typing
import importlib
import pkgutil
import os.path

import async_timeout

from . import device, devices

__all__ = [
    "DeviceFinderCollection"
]


class DeviceFinderCollection:
    def __init__(self, config):
        self._finder_classes: typing.Dict[str, device.DeviceFinder.__class__] = {
            name: importlib.import_module("." + name, "castbot.devices").Finder
            for _, name, _ in pkgutil.iter_modules([os.path.dirname(devices.__file__)]) if name != "device"}
        self._finders = [self._finder_classes[device_config["type"]](device_config) for device_config in config]
        self._devices: typing.List[device.Device] = []

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
        self._devices = [d for devices in found_devices for d in devices if d]

    async def find_device_by_name(self, device_name):
        if not self._devices:
            await self.refresh_all_devices()
        found_devices = [d for d in self._devices if repr(d) == device_name]
        return found_devices[0] if found_devices else None

    async def list_all_devices(self):
        if not self._devices:
            await self.refresh_all_devices()
        return self._devices
