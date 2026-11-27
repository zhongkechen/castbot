import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from castbot.devices.chromecast import ChromecastDevice
from castbot.utils import LocalToken


class ChromecastTimeoutTest(unittest.IsolatedAsyncioTestCase):
    async def test_stale_cleanup_does_not_stop_the_current_stream(self):
        status = {"content_id": "http://castbot.invalid/stream/102/20"}
        receiver = SimpleNamespace(controller=SimpleNamespace(info=status), stop=Mock())
        # Device discovery may use a new wrapper around the same receiver.
        old_device, current_device = ChromecastDevice(receiver), ChromecastDevice(receiver)

        await old_device.on_close(LocalToken(101, 10))
        receiver.stop.assert_not_called()

        await current_device.on_close(LocalToken(102, 20))
        receiver.stop.assert_called_once()

    async def test_cleanup_leaves_another_app_alone(self):
        status = {"content_id": "https://media.example/another-video"}
        receiver = SimpleNamespace(controller=SimpleNamespace(info=status), stop=Mock())
        await ChromecastDevice(receiver).on_close(LocalToken(101, 10))
        receiver.stop.assert_not_called()
