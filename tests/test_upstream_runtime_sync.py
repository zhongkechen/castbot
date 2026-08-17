import unittest
from types import SimpleNamespace
from unittest.mock import patch

from pyrogram.raw.types import Document, MessageMediaDocument
from pyrogram.raw.types.storage.file_unknown import FileUnknown
from pyrogram.raw.types.upload import File

import castbot.http as http_module
from castbot.client import BotClient
from castbot.http import Http
from castbot.utils import LocalToken


class FakeSession:
    def __init__(self):
        self.request = None

    async def invoke(self, request, **_kwargs):
        self.request = request
        return File(type=FileUnknown(), mtime=0, bytes=b"data")


class FakeStreamResponse:
    def __init__(self, status):
        self.status = status
        self.headers = {}
        self.force_closed = False
        self.eof = False

    async def prepare(self, _request):
        return self

    async def write(self, _block):
        return None

    async def write_eof(self):
        self.eof = True

    def force_close(self):
        self.force_closed = True


class FakeBotClient:
    def __init__(self, message):
        self.message = message

    async def get_message(self, _message_id):
        return self.message

    async def get_block(self, _message, _offset, _block_size):
        return b"data"


class UpstreamRuntimeSyncTest(unittest.IsolatedAsyncioTestCase):
    async def test_get_block_forwards_document_file_reference(self):
        session = FakeSession()
        bot_client = BotClient.__new__(BotClient)
        bot_client._client = SimpleNamespace(media_sessions={4: session})
        bot_client._file_fake_fw_wait = 0
        document = SimpleNamespace(dc_id=4, id=1, access_hash=2, file_reference=b"telegram-reference")
        message = SimpleNamespace(media=SimpleNamespace(document=document))

        self.assertEqual(await bot_client.get_block(message, 0, 4), b"data")
        self.assertEqual(session.request.location.file_reference, b"telegram-reference")

    async def test_stream_response_forces_connection_close_after_eof(self):
        document = Document(
            id=1,
            access_hash=2,
            file_reference=b"reference",
            date=0,
            mime_type="video/mp4",
            size=4,
            dc_id=4,
            attributes=[],
        )
        message = SimpleNamespace(media=MessageMediaDocument(document=document))
        server = Http(
            {"listen_port": 8080, "listen_host": "127.0.0.1", "block_size": 4},
            FakeBotClient(message),
            [],
        )
        server._tokens[LocalToken(1, 2)] = object()
        server._feed_timeout = lambda *_args: None
        server._feed_downloaded_blocks = lambda *_args: None
        server._feed_stream_transport = lambda *_args: None
        request = SimpleNamespace(
            match_info={"message_id": "1", "token": "2"},
            headers={},
            method="GET",
            transport=SimpleNamespace(is_closing=lambda: False),
        )

        with patch.object(http_module, "StreamResponse", FakeStreamResponse):
            response = await server._stream_handler(request)

        self.assertTrue(response.eof)
        self.assertTrue(response.force_closed)
