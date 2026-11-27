"""Keep credentials out of application and access logs."""
import unittest

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from pyrogram.raw.types import Document, MessageMediaDocument

import castbot.http as http_module
from castbot.device import DeviceFinder
from castbot.devices.web import WebDeviceFinder
from castbot.http import Http
from castbot.utils import ConfigError, LocalToken


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


class SensitiveLogDataTest(unittest.IsolatedAsyncioTestCase):
    def test_device_finder_logs_discovery_without_configuration(self):
        config = {"type": "web", "password": "dummy-web-password"}
        with patch.object(DeviceFinder, "device_finder", set()):
            with self.assertLogs(level="INFO") as recorded:
                WebDeviceFinder(config)
                with self.assertRaises(ConfigError):
                    WebDeviceFinder(config)
        log = "\n".join(recorded.output)
        self.assertIn("DeviceFinder added: WebDeviceFinder", log)
        self.assertIn("Duplicate DeviceFinder config: WebDeviceFinder", log)
        self.assertNotIn(config["password"], log)

    async def test_stream_logs_exclude_token_and_headers_for_success_and_disconnect(self):
        token = LocalToken(123, 935871624)
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
        server._feed_downloaded_range = Mock()
        server._feed_stream_transport = Mock()
        request = SimpleNamespace(
            match_info={"message_id": "123", "token": str(token.token)},
            headers={"Authorization": "Bearer dummy-client-header"},
            method="GET", transport=SimpleNamespace(is_closing=lambda: False),
        )
        with patch.object(http_module, "StreamResponse", FakeStreamResponse):
            with self.assertLogs(level="INFO") as recorded:
                response = await server._stream_handler(request)
                bot_client.get_block.side_effect = ConnectionResetError
                await server._stream_handler(request)
        log = "\n".join(recorded.output)
        self.assertEqual(response.status, 200)
        self.assertIn("Incoming streaming request: GET message 123", log)
        self.assertIn("Broken streaming connection for message 123", log)
        self.assertNotIn(str(token), log)
        self.assertNotIn(str(token.token), log)
        self.assertNotIn("dummy-client-header", log)

    async def test_http_server_disables_logging_paths_with_credentials(self):
        server = Http({"listen_port": 8080, "listen_host": "127.0.0.1"}, None, [])
        with (
            patch.object(http_module.web, "AppRunner") as runner_factory,
            patch.object(http_module.web, "TCPSite") as site_factory,
        ):
            runner_factory.return_value.setup = AsyncMock()
            runner_factory.return_value.cleanup = AsyncMock()
            site_factory.return_value.start = AsyncMock(side_effect=asyncio.CancelledError)
            with self.assertRaises(asyncio.CancelledError):
                await server.start()
        self.assertIsNone(runner_factory.call_args.kwargs["access_log"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
