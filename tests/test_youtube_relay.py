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
from castbot.youtube import StreamOption, YouTubeRelayError, YouTubeStream
from castbot.youtube import list_youtube_streams, resolve_youtube_stream, youtube_video_id


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

    async def test_stream_listing_and_explicit_selection_use_compatible_format_filters(self):
        url = "https://rr1.example.googlevideo.com/videoplayback"
        metadata = b"\n".join(json.dumps(item).encode() for item in (
            {"format_id": "22", "height": 720, "fps": 30, "url": url},
            {"format_id": "18", "height": 360, "fps": 30, "url": url},
            {"format_id": "99", "height": 1080, "url": "https://example.invalid/video"},
        ))
        selected = json.dumps({"url": url, "title": "Video", "http_headers": {}}).encode()
        with patch("castbot.youtube._youtube_metadata", side_effect=[metadata, selected]) as get_metadata:
            options = await list_youtube_streams(VIDEO_ID)
            await resolve_youtube_stream(VIDEO_ID, format_id="22")
        self.assertEqual([option.value for option in options], ["22", "18"])
        self.assertEqual(options[0].label, "720p · 30 fps · MP4 (#22)")
        selectors = [call.args[1] for call in get_metadata.await_args_list]
        self.assertTrue(selectors[0].startswith("all["))
        self.assertTrue(selectors[1].endswith("[format_id='22']"))
        for selector in selectors:
            self.assertIn("[ext=mp4][vcodec^=avc1][acodec^=mp4a]", selector)


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

    async def test_inline_stream_selection_is_restored_and_used_for_the_relay(self):
        await self.videos.on_new_youtube(self.message, VIDEO_ID)
        stream = self.message.reply.call_args.kwargs["reply_markup"].inline_keyboard[2][0]
        self.assertEqual(stream.text, "STREAM")
        option = StreamOption("22", "720p · 30 fps · MP4 (#22)")
        with patch("castbot.video.list_youtube_streams", return_value=[option]) as list_streams:
            (await self.click(stream)).answer.assert_awaited_once()
            choices = self.control.edit_text.call_args.kwargs["reply_markup"].inline_keyboard
            self.assertEqual(choices[0][0].text, "✓ Auto")
            self.assertEqual(choices[1][0].text, option.label)
            (await self.click(choices[1][0])).answer.assert_awaited_once()
        list_streams.assert_awaited_once_with(VIDEO_ID)
        self.device.play.assert_not_awaited()
        text, = self.control.edit_text.await_args.args
        self.assertIn(f"Stream: {option.label}", text)

        self.videos._playing_videos.clear()
        self.control.text = text.replace("<code>", "").replace("</code>", "")
        self.control.reply_to_message_id = self.message.id
        self.bot.get_message.return_value = SimpleNamespace(id=self.message.id, media=None, message=WATCH_URL)
        play = self.control.edit_text.call_args.kwargs["reply_markup"].inline_keyboard[1][0]
        source = YouTubeStream(self.upstream.make_url("/media"), "Selected video", {})
        with patch("castbot.video.resolve_youtube_stream", return_value=source) as resolve:
            (await self.click(play)).answer.assert_awaited_once_with("Playing")
        resolve.assert_awaited_once_with(VIDEO_ID, format_id="22")
        relay_url, _, token = self.device.play.await_args.args
        try:
            async with self.client.head(urlsplit(relay_url).path) as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(response.headers["Content-Type"], "video/mp4")
        finally:
            self.http.remove_remote_token(token)

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

    async def test_replaying_with_another_format_rotates_the_relay_url(self):
        await self.videos.on_new_youtube(self.message, VIDEO_ID)
        video = next(iter(self.videos._playing_videos.values()))
        self.addAsyncCleanup(video.stop)
        source = YouTubeStream(self.upstream.make_url("/media"), "Test video", {})
        with patch("castbot.video.resolve_youtube_stream", return_value=source) as resolve:
            await video.play()
            old_url, _, old_token = self.device.play.await_args.args
            old_relay = self.http._tokens[old_token]
            await video.stop()
            with patch("castbot.video.list_youtube_streams", return_value=[StreamOption("22", "720p MP4 (#22)")]):
                await video.handle_stream_selection("pick22")
            await video.play()
            resolve.assert_awaited_with(VIDEO_ID, format_id="22")

        current_url, _, current_token = self.device.play.await_args.args
        self.assertNotEqual(current_url, old_url)
        self.assertNotEqual(current_token, video.local_token)
        self.assertIs(self.videos._playing_videos[video.local_token], video)
        await old_relay.close(None)
        self.device.on_close.assert_not_awaited()
        async with self.client.get(urlsplit(old_url).path, headers={"Range": "bytes=2-4"}) as response:
            self.assertEqual(response.status, 403)
        async with self.client.get(urlsplit(current_url).path, headers={"Range": "bytes=2-4"}) as response:
            self.assertEqual(response.status, 206)
            self.assertEqual(response.headers["Cache-Control"], "no-store")
            self.assertEqual(await response.read(), MEDIA[2:5])

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
