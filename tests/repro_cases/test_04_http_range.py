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
        self.closing = False

    async def prepare(self, request):
        if self.closing:
            self.headers["Connection"] = "close"
        return self

    async def write(self, block):
        self.body += block

    async def write_eof(self):
        pass

    def force_close(self):
        self.closing = True


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
    server._feed_downloaded_blocks = lambda *_: None
    server._feed_stream_transport = lambda *_: None
    return server, client


def make_request(message_id, token, range_header=None, method="GET"):
    return SimpleNamespace(match_info={"message_id": str(message_id), "token": str(token)},
                           headers={} if range_header is None else {"Range": range_header}, method=method,
                           transport=SimpleNamespace(is_closing=lambda: False))


class HttpRangeTest(unittest.IsolatedAsyncioTestCase):
    async def test_satisfiable_ranges_have_exact_body_and_headers(self):
        cases = [
            ("bytes=2-4", b"CDE", "bytes 2-4/8"),
            ("bytes=4-", b"EFGH", "bytes 4-7/8"),
            ("bytes=0-0", b"A", "bytes 0-0/8"),
            ("bytes=0-7", b"ABCDEFGH", "bytes 0-7/8"),
            ("bytes=-3", b"FGH", "bytes 5-7/8"),
            ("bytes=-20", b"ABCDEFGH", "bytes 0-7/8"),
            ("bytes=4-100", b"EFGH", "bytes 4-7/8"),
        ]
        for header, body, content_range in cases:
            with self.subTest(range=header):
                server, _ = make_server()
                with patch.object(http_module, "StreamResponse", CaptureStream):
                    response = await server._stream_handler(make_request(1, 2, header))
                self.assertEqual(response.status, 206)
                self.assertEqual(response.body, body)
                self.assertEqual(response.headers["Content-Range"], content_range)
                self.assertEqual(response.headers["Content-Length"], str(len(body)))
                self.assertEqual(response.headers["Connection"], "close")

    async def test_unsatisfiable_ranges_include_the_full_size(self):
        for header in ("bytes=8-", "bytes=4-2", "bytes=-0"):
            with self.subTest(range=header):
                server, _ = make_server()
                response = await server._stream_handler(make_request(1, 2, header))
                self.assertEqual(response.status, 416)
                self.assertEqual(response.headers["Content-Range"], "bytes */8")

    async def test_malformed_and_multiple_ranges_are_rejected(self):
        for header in ("bytes=-", "other bytes=2-4", "bytes=0-0,2-2"):
            with self.subTest(range=header):
                server, _ = make_server()
                response = await server._stream_handler(make_request(1, 2, header))
                self.assertEqual(response.status, 400)

    async def test_full_response_and_head_report_total_length(self):
        server, _ = make_server()
        with patch.object(http_module, "StreamResponse", CaptureStream):
            response = await server._stream_handler(make_request(1, 2))
        self.assertEqual(response.status, 200)
        self.assertEqual(response.body, b"ABCDEFGH")
        self.assertEqual(response.headers["Content-Length"], "8")
        self.assertNotIn("Content-Range", response.headers)

        response = await server._stream_handler(make_request(1, 2, "bytes=2-4", method="HEAD"))
        self.assertEqual(response.status, 200)
        self.assertIsNone(response.body)
        self.assertEqual(response.headers["Content-Length"], "8")
        self.assertNotIn("Content-Range", response.headers)


if __name__ == "__main__":
    unittest.main(verbosity=2)
