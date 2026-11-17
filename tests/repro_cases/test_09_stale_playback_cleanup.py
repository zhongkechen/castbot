"""Passing test confirms stale HTTP cleanup removes an active browser."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from castbot.devices.web import WebDevice
from castbot.http import Http
from castbot.utils import LocalToken
from castbot.video import PlayingVideos


class ActiveTransport:
    def is_closing(self):
        return False


class StalePlaybackCleanupRepro(unittest.IsolatedAsyncioTestCase):
    async def test_expired_a_unregisters_the_browser_used_by_active_b(self):
        devices = {}
        browser = WebDevice("repro browser", 10, devices)
        devices[10] = browser
        server = Http({"listen_port": 8080, "listen_host": "127.0.0.1", "block_size": 4}, None, [])
        videos = PlayingVideos(server, None, None)
        videos.set_user_device(1, browser)
        token_a, token_b = LocalToken(101, 1), LocalToken(102, 2)
        control_a = SimpleNamespace(edit_text=AsyncMock())
        control_b = SimpleNamespace(edit_text=AsyncMock())
        a = videos.new_video(token_a, 1, SimpleNamespace(id=101), control_message=control_a)
        b = videos.new_video(token_b, 1, SimpleNamespace(id=102), control_message=control_b)
        server.add_remote_token(a)
        uri_b = server.add_remote_token(b)
        server._stream_transports[token_b] = {ActiveTransport()}
        self.assertIs(a.playing_device, b.playing_device)
        await browser.play(uri_b, "B", token_b)
        self.assertEqual(browser.get_url_to_play(), uri_b)
        self.assertIn(10, devices)

        # Directly invoke the callback as if A's 900-second grace period elapsed.
        await server._timeout_handler(token_a, 8)

        self.assertNotIn(10, devices)
        self.assertNotIn(token_a, server._tokens)
        self.assertNotIn(token_a, videos._playing_videos)
        self.assertIn(token_b, server._tokens)
        self.assertIn(token_b, videos._playing_videos)
        self.assertFalse(next(iter(server._stream_transports[token_b])).is_closing())
        control_a.edit_text.assert_awaited_once()
        control_b.edit_text.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
