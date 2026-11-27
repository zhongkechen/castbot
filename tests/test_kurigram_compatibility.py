import contextlib
import inspect
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from pyrogram import Client
from pyrogram.crypto import aes
from pyrogram.raw.functions.auth import ExportAuthorization
from pyrogram.raw.functions.help import GetConfig
from pyrogram.raw.types import DcOption
from pyrogram.session import Auth, Session
from pyrogram.types import LinkPreviewOptions, Message, ReplyParameters

import castbot.client as client_module
from castbot.button import DeviceSelectButton, PlayButton, RetryButton
from castbot.client import BotClient
from castbot.downloader import DownloadedVideo, Downloader
from castbot.utils import LocalToken
from castbot.video import PlayingVideo


class KurigramCompatibilityTest(unittest.IsolatedAsyncioTestCase):
    def test_crypto_backend_is_enabled(self):
        self.assertIsNotNone(aes._crypto_backend)

    def test_inline_keyboard_buttons_set_callback_data(self):
        token = LocalToken(123, 456)
        playing_video = PlayingVideo(token, 1, SimpleNamespace())

        play_btn = PlayButton(playing_video).get_button()
        self.assertEqual(play_btn.callback_data, f"c:{token}:PLAY")
        self.assertIsNone(play_btn.icon_custom_emoji_id)

        select_btn = DeviceSelectButton("TV", playing_video).get_button()
        self.assertEqual(select_btn.callback_data, f"s:{token}:TV")
        self.assertIsNone(select_btn.icon_custom_emoji_id)

        retry_btn = RetryButton(SimpleNamespace()).get_button()
        self.assertEqual(retry_btn.callback_data, "r:RETRY")
        self.assertIsNone(retry_btn.icon_custom_emoji_id)

    async def test_reply_message_uses_reply_parameters(self):
        calls = []
        send_sig = inspect.signature(Client.send_message)

        async def fake_send_message(*args, **kwargs):
            send_sig.bind(object(), *args, **kwargs)
            calls.append((args, kwargs))

        bot_client = BotClient.__new__(BotClient)
        bot_client._client = SimpleNamespace(send_message=fake_send_message)

        await bot_client.reply_message(42, 100, "hello")

        self.assertEqual(len(calls), 1)
        args, kwargs = calls[0]
        self.assertEqual(args, (100,))
        self.assertIsInstance(kwargs["reply_parameters"], ReplyParameters)
        self.assertEqual(kwargs["reply_parameters"].message_id, 42)
        self.assertNotIn("reply_to_message_id", kwargs)

    async def test_start_initializes_kurigram_sessions_and_auth_with_server_address_and_port(self):
        session_sig = inspect.signature(Session.__init__)
        auth_sig = inspect.signature(Auth.__init__)
        created_sessions = []
        created_auths = []

        class FakeSession:
            def __init__(self, *args, **kwargs):
                bound = session_sig.bind(self, *args, **kwargs)
                bound.apply_defaults()
                self.bound = bound.arguments
                self.auth_key = bound.arguments["auth_key"]
                self.started = False
                self.imported = []
                created_sessions.append(self)

            async def start(self):
                self.started = True

            async def invoke(self, request):
                self.imported.append(request)

        class FakeAuth:
            def __init__(self, *args, **kwargs):
                bound = auth_sig.bind(self, *args, **kwargs)
                bound.apply_defaults()
                self.bound = bound.arguments
                created_auths.append(self)

            async def create(self):
                return f"auth-key-dc-{self.bound['dc_id']}".encode()

        dc_options = [
            DcOption(id=2, ip_address="149.154.167.51", port=443, ipv6=False, media_only=False, cdn=False),
            DcOption(id=4, ip_address="149.154.167.220", port=443, ipv6=False, media_only=True, cdn=False),
            DcOption(id=4, ip_address="149.154.167.91", port=443, ipv6=False, media_only=False, cdn=False),
            DcOption(id=203, ip_address="91.108.56.100", port=443, ipv6=False, media_only=False, cdn=True),
        ]

        class FakeStorage:
            async def dc_id(self):
                return 2

            async def auth_key(self):
                return b"main-auth-key"

            async def test_mode(self):
                return False

        class FakeClient:
            def __init__(self):
                self.storage = FakeStorage()
                self.media_sessions = {}
                self.ipv6 = False

            async def start(self):
                return self

            async def invoke(self, request):
                if isinstance(request, GetConfig):
                    return SimpleNamespace(dc_options=dc_options)
                if isinstance(request, ExportAuthorization):
                    return SimpleNamespace(id=99, bytes=b"exported")
                raise AssertionError(f"Unexpected invoke: {request!r}")

        with tempfile.TemporaryDirectory() as tmpdir:
            bot_client = BotClient.__new__(BotClient)
            bot_client._session_name = os.path.join(tmpdir, "castbot")
            bot_client._client = FakeClient()

            with (
                patch.object(client_module, "Session", FakeSession),
                patch.object(client_module, "Auth", FakeAuth),
            ):
                await bot_client.start()

            self.assertEqual(set(bot_client._client.media_sessions.keys()), {2, 4})
            self.assertEqual(len(created_auths), 1)
            self.assertEqual(created_auths[0].bound["dc_id"], 4)
            self.assertEqual(created_auths[0].bound["server_address"], "149.154.167.91")
            self.assertEqual(created_auths[0].bound["port"], 443)
            self.assertFalse(created_auths[0].bound["test_mode"])

            dc2_session = bot_client._client.media_sessions[2]
            dc4_session = bot_client._client.media_sessions[4]
            self.assertTrue(dc2_session.started)
            self.assertTrue(dc4_session.started)
            self.assertEqual(dc2_session.bound["server_address"], "149.154.167.51")
            self.assertEqual(dc2_session.bound["port"], 443)
            self.assertEqual(dc4_session.bound["server_address"], "149.154.167.91")
            self.assertEqual(dc4_session.bound["port"], 443)
            self.assertEqual(len(dc4_session.imported), 1)

    async def test_downloader_reply_and_reply_video_match_kurigram_signatures(self):
        reply_sig = inspect.signature(Message.reply)
        reply_video_sig = inspect.signature(Message.reply_video)
        reply_calls = []
        reply_video_calls = []

        class FakeReplyMessage:
            def __init__(self):
                self.edits = []
                self.deleted = False

            async def edit_text(self, text, **kwargs):
                self.edits.append((text, kwargs))

            async def delete(self):
                self.deleted = True

        fake_reply_message = FakeReplyMessage()

        class FakeMessage:
            id = 77

            async def reply(self, *args, **kwargs):
                reply_sig.bind(self, *args, **kwargs)
                reply_calls.append((args, kwargs))
                return fake_reply_message

            async def reply_video(self, *args, **kwargs):
                reply_video_sig.bind(self, *args, **kwargs)
                reply_video_calls.append((args, kwargs))
                args[0].close()
                return SimpleNamespace(id=88)

        on_new_video_calls = []

        class FakePlayingVideos:
            async def on_new_video(self, client, video_message, link_message=None):
                on_new_video_calls.append((client, video_message, link_message))

        with tempfile.TemporaryDirectory() as tmpdir:
            video_path = os.path.join(tmpdir, "video.mp4")
            with open(video_path, "wb") as handle:
                handle.write(b"fake-video")

            downloader = Downloader({}, playing_videos=FakePlayingVideos())

            @contextlib.asynccontextmanager
            async def fake_download(_url):
                yield DownloadedVideo(
                    video_filename=video_path,
                    thumbnail_filename=None,
                    title="Demo",
                    width=1280,
                    height=720,
                    duration=10,
                )

            downloader.download = fake_download
            await downloader.download_url(FakeMessage(), "https://example.com/video")

        self.assertEqual(len(reply_calls), 1)
        self.assertIsInstance(reply_calls[0][1]["link_preview_options"], LinkPreviewOptions)
        self.assertTrue(reply_calls[0][1]["link_preview_options"].is_disabled)
        self.assertEqual(len(reply_video_calls), 1)
        self.assertEqual(reply_video_calls[0][1]["caption"], "Demo")
        self.assertTrue(fake_reply_message.deleted)
        self.assertEqual(len(on_new_video_calls), 1)
