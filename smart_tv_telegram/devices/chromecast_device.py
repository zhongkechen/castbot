import asyncio
import concurrent.futures
import functools
import typing

import catt.api

from . import Device, DeviceFinder, RoutersDefType, DevicePlayerFunction
from .. import Config

__all__ = [
    "ChromecastDevice",
    "ChromecastDeviceFinder"
]

_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=1)


async def run_method_in_executor(func, *args, **kwargs):
    partial_function = functools.partial(func, *args, **kwargs)
    return await asyncio.get_event_loop().run_in_executor(_EXECUTOR, partial_function)


class ChromecastPlayFunction(DevicePlayerFunction):
    _device: catt.api.CattDevice

    def __init__(self, device: catt.api.CattDevice):
        self._device = device

    async def get_name(self) -> str:
        return "PLAY"

    async def handle(self):
        await run_method_in_executor(self._device.play)


class ChromecastPauseFunction(DevicePlayerFunction):
    _device: catt.api.CattDevice

    def __init__(self, device: catt.api.CattDevice):
        self._device = device

    async def get_name(self) -> str:
        return "PAUSE"

    async def handle(self):
        await run_method_in_executor(self._device.pause)


class ChromecastDevice(Device):
    _device: catt.api.CattDevice

    def __init__(self, device: catt.api.CattDevice):
        self._device = device

    def get_device_name(self) -> str:
        return self._device.name

    async def stop(self):
        pass

    async def on_close(self, local_token: int):
        await run_method_in_executor(self._device.stop)

    async def play(self, url: str, title: str, local_token: int):
        await run_method_in_executor(self._device.play_url, url, title=title)

    def get_player_functions(self) -> typing.List[DevicePlayerFunction]:
        return [
            ChromecastPlayFunction(self._device),
            ChromecastPauseFunction(self._device)
        ]


class ChromecastDeviceFinder(DeviceFinder):
    def __init__(self, config):
        self._enabled = bool(config["enabled"])
        self._devices_cache: typing.Dict[str, catt.api.CattDevice] = {}

    async def find(self) -> typing.List[Device]:
        if not self._enabled:
            return []
        found_devices: typing.List[catt.api.CattDevice] = await run_method_in_executor(catt.api.discover)
        cached_devices: typing.List[catt.api.CattDevice] = []

        for found_device in found_devices:
            cached_devices.append(self._devices_cache.setdefault(found_device.ip_addr, found_device))

        return [ChromecastDevice(device) for device in cached_devices]
