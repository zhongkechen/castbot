import typing

from smart_tv_telegram import Config
from smart_tv_telegram.devices import DeviceFinder, UpnpDeviceFinder, ChromecastDeviceFinder, VlcDeviceFinder, \
    WebDeviceFinder, XbmcDeviceFinder

__all__ = [
    "DeviceFinderCollection",
    "device_finder"
]


class DeviceFinderCollection:
    _finders: typing.List[DeviceFinder]

    def __init__(self):
        self._finders = []

    def register_finder(self, finder: DeviceFinder):
        self._finders.append(finder)

    def get_finders(self, config: Config) -> typing.List[DeviceFinder]:
        return [finder for finder in self._finders if finder.is_enabled(config)]


device_finder = DeviceFinderCollection()
device_finder.register_finder(UpnpDeviceFinder())
device_finder.register_finder(ChromecastDeviceFinder())
device_finder.register_finder(VlcDeviceFinder())
device_finder.register_finder(WebDeviceFinder())
device_finder.register_finder(XbmcDeviceFinder())
