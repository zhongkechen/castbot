import asyncio
import typing

import async_timeout

from smart_tv_telegram.devices import DeviceFinder, UpnpDeviceFinder, ChromecastDeviceFinder, VlcDeviceFinder, \
    WebDeviceFinder, XbmcDeviceFinder, Device

__all__ = [
    "DeviceFinderCollection"
]


class DeviceFinderCollection:
    def __init__(self, config):
        self.device_request_timeout = int(config.get("device_request_timeout", 10))
        self._finders: typing.List[DeviceFinder] = [
            UpnpDeviceFinder(config["upnp"]),
            ChromecastDeviceFinder(config["chromecast"]),
            VlcDeviceFinder(config["vlc"]),
            WebDeviceFinder(config["web"]),
            XbmcDeviceFinder(config["xbmc"])]
        self._devices: typing.List[Device] = []

    def get_all_routers(self):
        for finder in self._finders:
            routers = finder.get_routers()

            for handler in routers:
                yield handler.get_method(), handler.get_path(), handler.handle

    async def refresh_all_devices(self):
        self._devices = []
        for finder in self._finders:
            try:
                with async_timeout.timeout(self.device_request_timeout + 1):
                    self._devices.extend(await finder.find())
            except asyncio.CancelledError:
                pass

    async def find_device_by_name(self, device_name):
        if not self._devices:
            await self.refresh_all_devices()
        devices = [device for device in self._devices if repr(device) == device_name]
        return devices[0] if devices else None

    async def list_all_devices(self):
        if not self._devices:
            await self.refresh_all_devices()
        return self._devices
