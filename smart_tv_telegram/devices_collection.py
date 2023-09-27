import asyncio
import typing

import async_timeout

from smart_tv_telegram import Config
from smart_tv_telegram.devices import DeviceFinder, UpnpDeviceFinder, ChromecastDeviceFinder, VlcDeviceFinder, \
    WebDeviceFinder, XbmcDeviceFinder, Device

__all__ = [
    "DeviceFinderCollection",
    "device_finder"
]


class DeviceFinderCollection:
    _finders: typing.List[DeviceFinder]

    def __init__(self):
        self._finders = []
        self._devices: typing.List[Device] = []

    def register_finder(self, finder: DeviceFinder):
        self._finders.append(finder)

    def get_finders(self, config: Config) -> typing.List[DeviceFinder]:
        return [finder for finder in self._finders if finder.is_enabled(config)]

    async def refresh_all_devices(self, config: Config):
        self._devices = []
        for finder in self.get_finders(config):
            try:
                with async_timeout.timeout(config.device_request_timeout + 1):
                    self._devices.extend(await finder.find(config))
            except asyncio.CancelledError:
                pass

    async def find_device_by_name(self, config, device_name):
        if not self._devices:
            await self.refresh_all_devices(config)
        devices = [device for device in self._devices if repr(device) == device_name]
        return devices[0] if devices else None

    async def list_all_devices(self, config):
        if not self._devices:
            await self.refresh_all_devices(config)
        return self._devices


device_finder = DeviceFinderCollection()
device_finder.register_finder(UpnpDeviceFinder())
device_finder.register_finder(ChromecastDeviceFinder())
device_finder.register_finder(VlcDeviceFinder())
device_finder.register_finder(WebDeviceFinder())
device_finder.register_finder(XbmcDeviceFinder())
