"""Passing test confirms STOP is indistinguishable from an idle Web poll."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from castbot.devices.web import WebDevice, WebDeviceApiRequestPoll
from castbot.utils import LocalToken
from castbot.video import PlayingVideo


class WebStopCommandRepro(unittest.IsolatedAsyncioTestCase):
    async def test_playing_video_stop_produces_only_an_idle_poll(self):
        devices = {}
        browser = WebDevice("repro browser", 10, devices)
        devices[10] = browser
        poll = WebDeviceApiRequestPoll(devices)
        request = SimpleNamespace(match_info={"remote_token": "10"})
        token = LocalToken(123, 456)
        control = SimpleNamespace(edit_text=AsyncMock())
        video = PlayingVideo(token, 1, None, browser, SimpleNamespace(id=123), control_message=control)
        idle_before_play = await poll.handle(request)
        await browser.play("http://example.invalid/stream/123/456", "repro", token)
        playing_poll = await poll.handle(request)
        self.assertEqual(playing_poll.status, 200)
        self.assertIsNotNone(playing_poll.body)

        await video.stop()
        after_stop = await poll.handle(request)

        self.assertEqual((idle_before_play.status, idle_before_play.body), (302, None))
        self.assertEqual((after_stop.status, after_stop.body), (302, None))
        self.assertEqual(after_stop.status, idle_before_play.status)
        self.assertIsNone(browser.get_url_to_play())
        self.assertIn(10, devices)
        control.edit_text.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
