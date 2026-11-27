import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from castbot.device import PlaybackStatus
from castbot.devices.web import WebDevice, WebDeviceApiRequestPlaybackEvent, WebDeviceApiRequestPoll
from castbot.utils import LocalToken


class WebPlaybackStatusTest(unittest.IsolatedAsyncioTestCase):
    async def test_polling_does_not_count_as_playback_and_a_rejected_start_is_terminal(self):
        devices = {}
        browser = devices[42] = WebDevice("Browser", 42, devices)
        poll = WebDeviceApiRequestPoll(devices)
        report = WebDeviceApiRequestPlaybackEvent(devices)

        async def event(name, url):
            response = await report.handle(SimpleNamespace(
                match_info={"remote_token": "42", "event": name},
                text=AsyncMock(return_value=url),
            ))
            self.assertEqual(response.status, 204)

        first = "http://castbot.invalid/stream/10/1"
        second = "http://castbot.invalid/stream/10/2"
        poll_request = SimpleNamespace(match_info={"remote_token": "42"})
        await browser.play(first, "First", LocalToken(10, 1))
        self.assertEqual((await poll.handle(poll_request)).text, first)
        self.assertEqual(await browser.playlist_status(first), PlaybackStatus.BUFFERING)
        await event("error", first)
        self.assertEqual(await browser.playlist_status(first), PlaybackStatus.INTERRUPTED)

        await browser.play(second, "Second", LocalToken(10, 2))
        self.assertEqual((await poll.handle(poll_request)).text, second)
        await event("error", first)
        self.assertEqual(await browser.playlist_status(second), PlaybackStatus.BUFFERING)
        await event("playing", second)
        self.assertEqual(await browser.playlist_status(second), PlaybackStatus.ACTIVE)
        await event("ended", second)
        await event("playing", second)
        self.assertEqual(await browser.playlist_status(second), PlaybackStatus.FINISHED)
