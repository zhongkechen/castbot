"""Verify Web playback cleanup preserves the browser registration."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from castbot.devices.web import WebDevice
from castbot.http import Http
from castbot.utils import DeviceControlError, LocalToken
from castbot.video import PlayingVideos


class ActiveTransport:
    def is_closing(self):
        return False


class StalePlaybackCleanupTest(unittest.IsolatedAsyncioTestCase):
    async def test_expired_stream_does_not_unregister_active_browser(self):
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
        await browser.play("http://example.invalid/stream/101/1", "A", token_a)
        await browser.play(uri_b, "B", token_b)
        self.assertEqual(browser.get_url_to_play(), uri_b)
        self.assertIn(10, devices)

        # Directly invoke the callback as if A's 900-second grace period elapsed.
        await server._timeout_handler(token_a, 8)

        self.assertIs(devices[10], browser)
        self.assertNotIn(token_a, server._tokens)
        self.assertNotIn(token_a, videos._playing_videos)
        self.assertIn(token_b, server._tokens)
        self.assertIn(token_b, videos._playing_videos)
        self.assertFalse(next(iter(server._stream_transports[token_b])).is_closing())
        control_a.edit_text.assert_awaited_once()
        control_b.edit_text.assert_not_awaited()

        # Cleaning up the current stream stops playback and retains the registered browser.
        server._stream_transports[token_b].clear()
        await server._timeout_handler(token_b, 8)
        self.assertIs(devices[10], browser)
        self.assertTrue(browser.consume_stop())
        self.assertNotIn(token_b, server._tokens)
        self.assertNotIn(token_b, videos._playing_videos)
        control_b.edit_text.assert_awaited_once()

        await browser.play(uri_b, "Replay", token_b)
        self.assertEqual(browser.get_url_to_play(), uri_b)

    async def test_deregistered_browser_rejects_a_play_command(self):
        devices = {}
        stale = devices[10] = WebDevice("Browser", 10, devices)
        del devices[10]
        current = devices[20] = WebDevice("Browser", 20, devices)

        with self.assertRaisesRegex(DeviceControlError, "Select the registered player again"):
            await stale.play("http://example.invalid/stream/101/1", "A", LocalToken(101, 1))
        self.assertIsNone(current.get_url_to_play())


if __name__ == "__main__":
    unittest.main()
