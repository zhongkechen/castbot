from types import SimpleNamespace
import unittest
from unittest.mock import patch
from pyrogram.raw.types import Document, MessageMediaDocument
import castbot.http as http_module
from castbot.http import Http
from castbot.utils import LocalToken


class CaptureStream:
    def __init__(self, status):
        self.status = status
        self.headers = {}
        self.body = b""

    async def prepare(self, request):
        return self

    async def write(self, block):
        self.body += block

    async def write_eof(self):
        pass

    def force_close(self):
        pass


class FakeClient:
    def __init__(self):
        self.requested_ids = []

    async def get_message(self, message_id):
        self.requested_ids.append(message_id)
        document = Document(id=message_id, access_hash=2, file_reference=b"dummy-reference", date=0,
                            mime_type="video/mp4", size=8, dc_id=4, attributes=[])
        return SimpleNamespace(media=MessageMediaDocument(document=document))

    async def get_block(self, message, offset, block_size):
        return b"ABCDEFGH"[offset:offset + block_size]


def make_server():
    client = FakeClient()
    server = Http({"listen_host": "127.0.0.1", "listen_port": 8080, "block_size": 4}, client, [])
    server._tokens[LocalToken(1, 2)] = object()
    server._feed_timeout = lambda *_: None
    server._feed_downloaded_range = lambda *_: None
    server._feed_stream_transport = lambda *_: None
    return server, client


def make_request(message_id, token, range_header=None):
    return SimpleNamespace(match_info={"message_id": str(message_id), "token": str(token)},
                           headers={} if range_header is None else {"Range": range_header}, method="GET",
                           transport=SimpleNamespace(is_closing=lambda: False))


class MediaTokenScopeTest(unittest.IsolatedAsyncioTestCase):
    async def test_out_of_range_token_is_rejected_before_fetching_media(self):
        server, client = make_server()
        response = await server._stream_handler(make_request(2, (1 << 64) + 2))
        self.assertEqual(response.status, 403)
        self.assertEqual(client.requested_ids, [])

    async def test_registered_token_still_streams_media(self):
        server, client = make_server()
        with patch.object(http_module, "StreamResponse", CaptureStream):
            response = await server._stream_handler(make_request(1, 2))
        self.assertEqual(response.status, 200)
        self.assertEqual(response.body, b"ABCDEFGH")
        self.assertEqual(client.requested_ids, [1])

    def test_token_identity_and_wire_format(self):
        token = LocalToken(1, 0)
        self.assertEqual(token.token, 0)
        self.assertEqual(str(token), "10000000000000000")
        self.assertEqual(token, LocalToken.deserialize(str(token)))
        self.assertNotEqual(token, LocalToken(2, 0))
        self.assertNotEqual(token, LocalToken(1, 1))

    async def test_unrelated_normal_token_is_rejected(self):
        server, client = make_server()
        response = await server._stream_handler(make_request(2, 2))
        self.assertEqual(response.status, 403)
        self.assertEqual(client.requested_ids, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
