"""Passing tests confirm dummy device credentials and media tokens reach logs."""
import re
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from pyrogram.raw.types import Document, MessageMediaDocument

import castbot.http as http_module
from castbot.device import DeviceFinder
from castbot.devices.web import WebDeviceFinder
from castbot.http import Http
from castbot.utils import LocalToken


class FakeStreamResponse:
    def __init__(self, status):
        self.status = status
        self.headers = {}

    async def prepare(self, _request):
        return self

    async def write(self, _data):
        pass

    async def write_eof(self):
        pass

    def force_close(self):
        pass


class SensitiveLogDataRepro(unittest.IsolatedAsyncioTestCase):
    def test_device_finder_logs_a_supplied_dummy_password(self):
        config = {"type": "web", "password": "dummy-web-password"}
        with patch.object(DeviceFinder, "device_finder", set()):
            with self.assertLogs(level="INFO") as recorded:
                WebDeviceFinder(config)
        log = "\n".join(recorded.output)
        self.assertIn("DeviceFinder added:", log)
        self.assertIn(config["password"], log)
        print("Observed: the device startup log includes the dummy password verbatim.")

    async def test_real_stream_handler_logs_reversible_token_and_request_headers(self):
        token = LocalToken(123, 456)
        document = Document(
            id=7, access_hash=8, file_reference=b"dummy-reference", date=0,
            mime_type="video/mp4", size=4, dc_id=4, attributes=[],
        )
        message = SimpleNamespace(media=MessageMediaDocument(document=document))
        bot_client = SimpleNamespace(
            get_message=AsyncMock(return_value=message),
            get_block=AsyncMock(return_value=b"data"),
        )
        server = Http({"listen_port": 8080, "listen_host": "127.0.0.1", "block_size": 4}, bot_client, [])
        server._tokens[token] = object()
        server._feed_timeout = Mock()
        server._feed_downloaded_blocks = Mock()
        server._feed_stream_transport = Mock()
        request = SimpleNamespace(
            match_info={"message_id": "123", "token": "456"},
            headers={"Authorization": "Bearer dummy-client-header"},
            method="GET", transport=SimpleNamespace(is_closing=lambda: False),
        )
        with patch.object(http_module, "StreamResponse", FakeStreamResponse):
            with self.assertLogs(level="INFO") as recorded:
                response = await server._stream_handler(request)
        log = "\n".join(recorded.output)
        self.assertEqual(response.status, 200)
        observed = re.search(r"Incoming streaming request: GET ([0-9a-f]+) ", log)
        self.assertIsNotNone(observed)
        recovered = LocalToken.deserialize(observed.group(1))
        self.assertEqual((recovered.message_id, recovered.token), (123, 456))
        self.assertIn("dummy-client-header", log)
        bot_client.get_message.assert_awaited_once_with(123)
        print("Observed: the handler log reveals the full dummy media token and dummy Authorization header.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
