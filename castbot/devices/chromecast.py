import asyncio
import concurrent.futures
import functools
import typing
from urllib.parse import urlsplit

import catt.api

from ..utils import LocalToken
from ..device import Device, DeviceFinder, PlaybackStatus

__all__ = ["Finder"]

_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=1)


async def run_method_in_executor(func, *args, **kwargs):
    partial_function = functools.partial(func, *args, **kwargs)
    return await asyncio.get_event_loop().run_in_executor(_EXECUTOR, partial_function)


class ChromecastDevice(Device):
    _device: catt.api.CattDevice

    def __init__(self, device: catt.api.CattDevice):
        self._device = device

    def get_device_name(self) -> str:
        return self._device.name

    def get_device_key(self) -> str:
        return str(self._device.uuid or self._device.ip_addr)

    async def stop(self):
        await run_method_in_executor(self._device.stop)

    async def on_close(self, local_token: LocalToken):
        await run_method_in_executor(self._stop_closed_stream, local_token)

    def _stop_closed_stream(self, local_token: LocalToken):
        content_id = self._device.controller.info.get("content_id")
        if not isinstance(content_id, str):
            return
        try:
            path = urlsplit(content_id).path
        except ValueError:
            return
        if path == f"/stream/{local_token.message_id}/{local_token.token}":
            self._device.stop()

    async def play(self, url: str, title: str, local_token: LocalToken):
        await run_method_in_executor(self._device.play_url, url, title=title)

    async def playlist_status(self, url: str) -> PlaybackStatus:
        status = self._device.controller.info
        if status.get("content_id") != url:
            return PlaybackStatus.INTERRUPTED
        state = status.get("player_state")
        if state in {"PLAYING", "PAUSED"}:
            return PlaybackStatus.ACTIVE
        if state == "IDLE":
            return PlaybackStatus.FINISHED if status.get("idle_reason") == "FINISHED" else PlaybackStatus.INTERRUPTED
        return PlaybackStatus.BUFFERING

    async def resume(self):
        await run_method_in_executor(self._device.play)

    async def pause(self):
        await run_method_in_executor(self._device.pause)


class ChromecastDeviceFinder(DeviceFinder):
    def __init__(self, config):
        super().__init__(config)
        self._devices_cache: typing.Dict[str, catt.api.CattDevice] = {}

    async def find(self) -> typing.List[Device]:
        found_devices: typing.List[catt.api.CattDevice] = await run_method_in_executor(catt.api.discover)
        cached_devices: typing.List[catt.api.CattDevice] = []

        for found_device in found_devices:
            cached_devices.append(self._devices_cache.setdefault(found_device.ip_addr, found_device))

        return [ChromecastDevice(device) for device in cached_devices]


Finder = ChromecastDeviceFinder
