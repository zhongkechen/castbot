import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from urllib.parse import urlsplit

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from castbot.button import Buttons
from castbot.downloader import Downloader
from castbot.http import Http
from castbot.video import PlayingVideos
from castbot.youtube import resolve_youtube_stream, youtube_video_id, YouTubeRelayError


VIDEO_ID = "M7lc1UVf-VE"
WATCH_URL = f"https://www.youtube.com/watch?v={VIDEO_ID}"
MEDIA = b"0123456789"


class YouTubeResolverTest(unittest.IsolatedAsyncioTestCase):
    def test_only_single_video_links_on_supported_hosts_are_recognized(self):
        for url in (WATCH_URL + "&list=PL123", f"https://youtu.be/{VIDEO_ID}?si=example",
                    f"https://m.youtube.com/shorts/{VIDEO_ID}"):
            with self.subTest(url=url):
                self.assertEqual(youtube_video_id(url), VIDEO_ID)
        self.assertIsNone(youtube_video_id("https://www.youtube.com/playlist?list=PL123"))
        self.assertIsNone(youtube_video_id(f"https://youtube.com.example/watch?v={VIDEO_ID}"))

    async def test_resolver_selects_a_local_relay_source_without_downloading(self):
        media_url = "https://rr1.example.googlevideo.com/videoplayback?sig=first%2Fsecond"
        process = SimpleNamespace(
            returncode=0,
            communicate=AsyncMock(return_value=(json.dumps({
                "url": media_url, "title": "Test video",
                "http_headers": {"User-Agent": "test-player", "Connection": "upgrade"},
            }).encode(), None)),
        )
        with patch("castbot.youtube.asyncio.create_subprocess_exec", return_value=process) as spawn:
            source = await resolve_youtube_stream(VIDEO_ID)
        command = spawn.call_args.args
        self.assertIn("--simulate", command)
        self.assertIn("--no-playlist", command)
        self.assertEqual(command[-2:], ("--", WATCH_URL))
        self.assertEqual(str(source.url), media_url)
        self.assertEqual(source.headers, {"User-Agent": "test-player"})

        process.returncode = 1
        with patch("castbot.youtube.asyncio.create_subprocess_exec", return_value=process):
            with self.assertRaises(YouTubeRelayError):
                await resolve_youtube_stream(VIDEO_ID)


class YouTubeRelayTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.upstream_requests = []
        self.release_body = asyncio.Event()
        upstream = web.Application()
        upstream.router.add_get("/media", self.upstream_media)
        self.upstream = TestServer(upstream)
        await self.upstream.start_server()
        self.addAsyncCleanup(self.upstream.close)

        self.bot = SimpleNamespace(get_message=AsyncMock())
        self.http = Http({"listen_host": "127.0.0.1", "listen_port": 8350}, self.bot, [])
        relay = web.Application()
        relay.router.add_get("/stream/{message_id}/{token}", self.http._stream_handler)
        self.client = TestClient(TestServer(relay))
        await self.client.start_server()
        self.addAsyncCleanup(self.client.close)

        self.control = SimpleNamespace(edit_text=AsyncMock())
        self.message = SimpleNamespace(
            text=WATCH_URL, id=17, from_user=SimpleNamespace(id=4),
            reply=AsyncMock(return_value=self.control), reply_video=AsyncMock(),
        )
        self.device = SimpleNamespace(
            get_device_name=lambda: "Example TV", stop=AsyncMock(), play=AsyncMock(), on_close=AsyncMock(),
            get_device_id=lambda: "4b19f2dd42a319df7c20",
        )
        self.finders = SimpleNamespace(
            find_device_by_name=AsyncMock(return_value=self.device),
            find_device_by_id=AsyncMock(return_value=self.device),
        )
        self.videos = PlayingVideos(self.http, self.finders, self.bot)
        self.videos.set_user_device(self.message.from_user.id, self.device)
        self.downloader = Downloader({}, self.videos)
        self.buttons = Buttons(self.videos, self.finders, self.downloader)

    async def upstream_media(self, request):
        byte_range = request.headers.get("Range")
        self.upstream_requests.append((request.method, byte_range, request.headers.get("User-Agent")))
        headers = {"Accept-Ranges": "bytes"}
        if byte_range == "bytes=2-4":
            headers["Content-Range"] = "bytes 2-4/10"
            return web.Response(status=206, body=MEDIA[2:5], headers=headers)
        if byte_range == "bytes=20-":
            return web.Response(status=416, headers={"Content-Range": "bytes */10"})
        if request.method == "GET":
            response = web.StreamResponse(headers={**headers, "Content-Length": str(len(MEDIA))})
            await response.prepare(request)
            await response.write(MEDIA[:3])
            await self.release_body.wait()
            await response.write(MEDIA[3:])
            return response
        return web.Response(body=MEDIA, headers=headers)

    async def click(self, button):
        callback = SimpleNamespace(
            from_user=self.message.from_user, message=self.control, data=button.callback_data, answer=AsyncMock(),
        )
        await self.buttons.on_button_click(None, callback)
        return callback

    async def test_link_handler_and_play_button_relay_head_get_and_range_until_stop(self):
        await self.downloader.on_new_link(None, self.message)
        await asyncio.gather(*self.downloader._download_tasks)
        markup = self.message.reply.call_args.kwargs["reply_markup"].inline_keyboard
        play = markup[1][0]
        self.message.reply_video.assert_not_awaited()
        self.assertEqual(self.upstream_requests, [])

        process = SimpleNamespace(
            returncode=0,
            communicate=AsyncMock(return_value=(json.dumps({
                "url": str(self.upstream.make_url("/media")),
                "title": "Test video",
                "http_headers": {"User-Agent": "test-player"},
            }).encode(), None)),
        )
        with (
            patch("castbot.youtube._is_youtube_media_url", return_value=True),
            patch("castbot.youtube.asyncio.create_subprocess_exec", return_value=process),
        ):
            callback = await self.click(play)
        callback.answer.assert_awaited_once_with("Playing")
        url, title, token = self.device.play.call_args.args
        self.addCleanup(self.http.remove_remote_token, token)
        self.assertEqual(urlsplit(url).netloc, "127.0.0.1:8350")
        self.assertEqual(title, "Test video")
        path = urlsplit(url).path
        self.assertEqual(self.upstream_requests, [])

        async with self.client.head(path) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(response.headers["Content-Length"], "10")
            self.assertEqual(response.headers["Content-Type"], "video/mp4")
            self.assertEqual(await response.read(), b"")
        async with self.client.get(path, headers={"Range": "bytes=2-4"}) as response:
            self.assertEqual(response.status, 206)
            self.assertEqual(response.headers["Content-Range"], "bytes 2-4/10")
            self.assertEqual(response.headers["Content-Length"], "3")
            self.assertEqual(await response.read(), MEDIA[2:5])
        async with self.client.get(path, headers={"Range": "bytes=20-"}) as response:
            self.assertEqual(response.status, 416)
            self.assertEqual(response.headers["Content-Range"], "bytes */10")
        self.addCleanup(self.release_body.set)
        async with asyncio.timeout(5), self.client.get(path) as response:
            self.assertEqual(response.status, 200)
            try:
                self.assertEqual(await response.content.readexactly(3), MEDIA[:3])
            finally:
                self.release_body.set()
            self.assertEqual(await response.read(), MEDIA[3:])
        async with self.client.get(f"/stream/{token.message_id}/{token.token ^ 1}") as response:
            self.assertEqual(response.status, 403)
        self.assertEqual(self.upstream_requests, [
            ("HEAD", None, "test-player"), ("GET", "bytes=2-4", "test-player"),
            ("GET", "bytes=20-", "test-player"), ("GET", None, "test-player"),
        ])
        self.bot.get_message.assert_not_awaited()

        stop = self.control.edit_text.call_args.kwargs["reply_markup"].inline_keyboard[0][0]
        await self.click(stop)
        async with self.client.get(path) as response:
            self.assertEqual(response.status, 403)
        self.assertEqual(len(self.upstream_requests), 4)

    async def test_reconstructs_youtube_controller_from_original_text_message(self):
        await self.videos.on_new_youtube(self.message, VIDEO_ID)
        video = next(iter(self.videos._playing_videos.values()))
        self.videos.remove(video)
        self.bot.get_message.return_value = SimpleNamespace(id=self.message.id, media=None, message=WATCH_URL)
        self.control.reply_to_message_id = self.message.id
        play = self.message.reply.call_args.kwargs["reply_markup"].inline_keyboard[1][0]
        button = await self.buttons.create_button_from_callback(
            SimpleNamespace(data=play.callback_data, from_user=self.message.from_user, message=self.control),
        )
        self.assertEqual(button.playing_video.youtube_id, VIDEO_ID)
        self.assertIs(button.playing_video.playing_device, self.device)
        self.finders.find_device_by_id.assert_awaited_once_with(self.device.get_device_id())
