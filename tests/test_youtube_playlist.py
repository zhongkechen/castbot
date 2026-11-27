import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from urllib.parse import urlsplit

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from castbot.button import Buttons
from castbot.device import PlaybackStatus
from castbot.devices.chromecast import ChromecastDevice
from castbot.devices.upnp import UpnpDevice
from castbot.devices.vlc import VlcDevice, _read_status
from castbot.devices.web import WebDevice, WebDeviceApiRequestPlaybackEvent, WebDeviceApiRequestPoll
from castbot.devices.xbmc import XbmcDevice
from castbot.downloader import Downloader
from castbot.http import Http
from castbot.utils import LocalToken
from castbot.video import PlayingVideos
from castbot.youtube import YouTubeRelayError, YouTubeStream, iter_youtube_playlist


PLAYLIST_ID = "PLTest123"
PLAYLIST_URL = f"https://www.youtube.com/playlist?list={PLAYLIST_ID}"
VIDEO_IDS = ("M7lc1UVf-VE", "jNQXAC9IVRw")
RELAY_URL = "http://castbot.invalid/stream/17/123"


class PlaylistResolverTest(unittest.IsolatedAsyncioTestCase):
    async def test_reads_entries_in_order_and_closes_lazy_extractor(self):
        process = SimpleNamespace(
            stdout=SimpleNamespace(readline=AsyncMock(side_effect=[b"NA\n", f"{VIDEO_IDS[0]}\n".encode()])),
            returncode=None,
            communicate=AsyncMock(),
        )
        process.kill = lambda: setattr(process, "returncode", -9)
        with patch("castbot.youtube.asyncio.create_subprocess_exec", return_value=process) as spawn:
            entries = iter_youtube_playlist(PLAYLIST_ID)
            self.assertEqual(await anext(entries), VIDEO_IDS[0])
            await entries.aclose()
        command = spawn.call_args.args
        self.assertIn("--flat-playlist", command)
        self.assertIn("--lazy-playlist", command)
        self.assertIn("--simulate", command)
        self.assertEqual(command[-2:], ("--", PLAYLIST_URL))
        self.assertEqual(process.returncode, -9)
        process.communicate.assert_awaited_once()


class PlaylistDeviceTest(unittest.IsolatedAsyncioTestCase):
    async def test_chromecast_requires_a_finished_status_for_the_current_url(self):
        info = {"content_id": RELAY_URL, "player_state": "IDLE", "idle_reason": "FINISHED"}
        device = ChromecastDevice(SimpleNamespace(controller=SimpleNamespace(info=info)))
        self.assertEqual(await device.playlist_status(RELAY_URL), PlaybackStatus.FINISHED)
        info["idle_reason"] = "CANCELLED"
        self.assertEqual(await device.playlist_status(RELAY_URL), PlaybackStatus.INTERRUPTED)

    async def test_upnp_checks_transport_state_and_track_uri(self):
        transport = {"CurrentTransportState": "PAUSED_PLAYBACK", "CurrentTransportStatus": "OK"}
        position = {"TrackURI": RELAY_URL}
        actions = {
            "GetTransportInfo": SimpleNamespace(async_call=AsyncMock(return_value=transport)),
            "GetPositionInfo": SimpleNamespace(async_call=AsyncMock(return_value=position)),
        }
        device = UpnpDevice.__new__(UpnpDevice)
        device._service = SimpleNamespace(action=actions.__getitem__)
        self.assertEqual(await device.playlist_status(RELAY_URL), PlaybackStatus.ACTIVE)
        position["TrackURI"] = "http://example.invalid/another"
        self.assertEqual(await device.playlist_status(RELAY_URL), PlaybackStatus.INTERRUPTED)
        transport["CurrentTransportState"] = "STOPPED"
        self.assertEqual(await device.playlist_status(RELAY_URL), PlaybackStatus.IDLE)

    async def test_vlc_status_parses_telnet_response_and_matches_the_current_url(self):
        reader = asyncio.StreamReader()
        reader.feed_data(f"> ( new input: {RELAY_URL} )\r\n( audio volume: 256 )\r\n( state paused )\r\n".encode())
        status = await _read_status(reader)
        device = VlcDevice.__new__(VlcDevice)
        device._call = AsyncMock(return_value=status)
        self.assertEqual(await device.playlist_status(RELAY_URL), PlaybackStatus.ACTIVE)
        self.assertEqual(await device.playlist_status("http://example.invalid/another"), PlaybackStatus.INTERRUPTED)
        device._call.return_value = "stopped", None
        self.assertEqual(await device.playlist_status(RELAY_URL), PlaybackStatus.IDLE)

    async def test_kodi_opens_the_relay_and_reports_when_its_player_goes_idle(self):
        device = XbmcDevice.__new__(XbmcDevice)
        device._call = AsyncMock(side_effect=[
            "OK", [{"type": "video", "playerid": 1}], {"item": {"file": RELAY_URL}}, [],
        ])
        await device.play_playlist_item(RELAY_URL, "video", LocalToken(17, 123))
        device._call.assert_awaited_once_with("Player.Open", item={"file": RELAY_URL}, options={"repeat": "off"})
        self.assertEqual(await device.playlist_status(RELAY_URL), PlaybackStatus.ACTIVE)
        self.assertEqual(await device.playlist_status(RELAY_URL), PlaybackStatus.IDLE)


class YouTubePlaylistTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        upstream = web.Application()

        async def media(request):
            return web.Response(body=request.match_info["video_id"].encode())

        upstream.router.add_get("/{video_id}", media)
        self.upstream = TestServer(upstream)
        await self.upstream.start_server()
        self.addAsyncCleanup(self.upstream.close)

        self.device = WebDevice("Browser", 42, {})
        devices = {42: self.device}
        self.control = SimpleNamespace(edit_text=AsyncMock())
        self.message = SimpleNamespace(
            text=PLAYLIST_URL, id=17, from_user=SimpleNamespace(id=4),
            reply=AsyncMock(return_value=self.control), reply_video=AsyncMock(),
        )
        self.http = Http({"listen_host": "127.0.0.1", "listen_port": 8350}, None, [])
        self.videos = PlayingVideos(self.http, None, None)
        self.videos.set_user_device(self.message.from_user.id, self.device)
        self.downloader = Downloader({}, self.videos)
        self.buttons = Buttons(self.videos, None, self.downloader)
        app = web.Application()
        app.router.add_get("/stream/{message_id}/{token}", self.http._stream_handler)
        for handler in (WebDeviceApiRequestPoll(devices), WebDeviceApiRequestPlaybackEvent(devices)):
            app.router.add_route(handler.get_method(), handler.get_path(), handler.handle)
        self.client = TestClient(TestServer(app))
        await self.client.start_server()
        self.addAsyncCleanup(self.client.close)
        self.addAsyncCleanup(self.videos.interrupt_playlist, self.device)
        self._entries_closed = asyncio.Event()
        self.entries_read = []
        self.resolve = AsyncMock(side_effect=self.resolve_item)
        for target, replacement in (
            ("castbot.playlist.iter_youtube_playlist", self.iter_entries),
            ("castbot.playlist.resolve_youtube_stream", self.resolve),
            ("castbot.playlist._POLL_INTERVAL", 0.01),
        ):
            patcher = patch(target, replacement)
            patcher.start()
            self.addCleanup(patcher.stop)

    async def iter_entries(self, playlist_id):
        self.assertEqual(playlist_id, PLAYLIST_ID)
        try:
            for video_id in VIDEO_IDS:
                self.entries_read.append(video_id)
                yield video_id
        finally:
            self._entries_closed.set()

    async def resolve_item(self, video_id):
        return YouTubeStream(self.upstream.make_url(f"/{video_id}"), video_id, {})

    async def click(self, button):
        callback = SimpleNamespace(
            from_user=self.message.from_user, message=self.control, data=button.callback_data, answer=AsyncMock(),
        )
        await self.buttons.on_button_click(None, callback)
        callback.answer.assert_awaited_once()
        return callback.answer.await_args.args[0]

    async def start_playlist(self):
        await self.downloader.on_new_link(None, self.message)
        await asyncio.gather(*self.downloader._download_tasks)
        play = self.message.reply.call_args.kwargs["reply_markup"].inline_keyboard[1][0]
        self.assertEqual(await self.click(play), "Playing")
        self.message.reply_video.assert_not_awaited()

    async def poll(self):
        async with self.client.get("/web/api/poll/42", allow_redirects=False) as response:
            return response.status, await response.text()

    async def play_url(self):
        async with asyncio.timeout(2):
            while True:
                status, url = await self.poll()
                if status == 200:
                    return url
                await asyncio.sleep(0.01)

    async def end(self, url):
        async with self.client.post("/web/api/playback/42/ended", data=url) as response:
            self.assertEqual(response.status, 204)

    async def assert_media(self, url, video_id):
        async with self.client.get(urlsplit(url).path) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(await response.text(), video_id)

    async def assert_revoked(self, url):
        async with self.client.get(urlsplit(url).path) as response:
            self.assertEqual(response.status, 403)

    async def test_streams_each_item_and_advances_only_when_the_device_finishes(self):
        await self.start_playlist()
        first = await self.play_url()
        await self.assert_media(first, VIDEO_IDS[0])
        self.assertEqual(self.entries_read, [VIDEO_IDS[0]])
        self.resolve.assert_awaited_once_with(VIDEO_IDS[0])
        self.assertEqual((await self.poll())[0], 302)

        await self.end(first)
        second = await self.play_url()
        self.assertNotEqual(first, second)
        await self.assert_revoked(first)
        await self.end(first)  # A late duplicate cannot end the new item.
        await self.assert_media(second, VIDEO_IDS[1])
        self.assertEqual(self.entries_read, list(VIDEO_IDS))
        self.assertIn("item 2", self.control.edit_text.await_args.args[0])

        playback = self.videos._playlists[self.device.get_device_id()][1]
        await self.end(second)
        await asyncio.wait_for(playback._task, 2)
        self.assertIn("Playlist finished.", self.control.edit_text.await_args.args[0])
        await self.assert_revoked(second)
        self.assertFalse(self.videos._playlists)
        self.assertTrue(self._entries_closed.is_set())

    async def test_stop_cancels_queue_and_revokes_the_active_stream(self):
        await self.start_playlist()
        first = await self.play_url()
        stop = self.control.edit_text.await_args.kwargs["reply_markup"].inline_keyboard[0][0]
        self.assertEqual(await self.click(stop), "Stopped")
        await self.end(first)
        self.assertEqual((await self.poll())[0], 204)
        await self.assert_revoked(first)
        self.assertTrue(self._entries_closed.is_set())
        self.assertFalse(self.videos._playlists)
        self.resolve.assert_awaited_once_with(VIDEO_IDS[0])

    async def test_playing_a_single_video_replaces_a_pending_playlist_transition(self):
        resolving_next = asyncio.Event()
        cancelled = asyncio.Event()

        async def resolve(video_id):
            if video_id == VIDEO_IDS[0]:
                return await self.resolve_item(video_id)
            resolving_next.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()
            raise AssertionError("The previous playlist should be cancelled.")

        self.resolve.side_effect = resolve
        await self.start_playlist()
        first = await self.play_url()
        await self.end(first)
        await asyncio.wait_for(resolving_next.wait(), 2)
        message = SimpleNamespace(id=18, from_user=self.message.from_user, reply=AsyncMock(return_value=self.control))
        await self.videos.on_new_youtube(message, VIDEO_IDS[1])
        single = next(video for video in self.videos._playing_videos.values() if video.youtube_id)
        source = await self.resolve_item(VIDEO_IDS[1])
        with patch("castbot.video.resolve_youtube_stream", return_value=source):
            await single.play()
        self.addAsyncCleanup(single.stop)
        self.assertTrue(cancelled.is_set())
        self.assertFalse(self.videos._playlists)
        await self.assert_revoked(first)
        await self.assert_media(await self.play_url(), VIDEO_IDS[1])

    async def test_skips_unavailable_entries_and_starts_the_next_video(self):
        self.resolve.side_effect = [YouTubeRelayError(), await self.resolve_item(VIDEO_IDS[1])]
        await self.start_playlist()
        url = await self.play_url()
        await self.assert_media(url, VIDEO_IDS[1])
        self.assertIn("item 2", self.control.edit_text.await_args.args[0])
        playback = self.videos._playlists[self.device.get_device_id()][1]
        await self.end(url)
        await asyncio.wait_for(playback._task, 2)
        self.assertIn("Skipped 1 unavailable video(s).", self.control.edit_text.await_args.args[0])
