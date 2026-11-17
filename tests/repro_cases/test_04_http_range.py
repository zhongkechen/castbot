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
    server._feed_downloaded_blocks = lambda *_: None
    server._feed_stream_transport = lambda *_: None
    return server, client


def make_request(message_id, token, range_header=None):
    return SimpleNamespace(match_info={"message_id": str(message_id), "token": str(token)},
                           headers={} if range_header is None else {"Range": range_header}, method="GET",
                           transport=SimpleNamespace(is_closing=lambda: False))


class HttpRangeRepro(unittest.IsolatedAsyncioTestCase):
    """Assertions intentionally record the defective responses, not the desired contract."""

    async def test_range_boundaries_return_wrong_body_or_length(self):
        cases = [
            ("bytes=2-4", b"CD", "bytes 2-4/8", b"CDE", 3),
            ("bytes=4-", b"EFGH", "bytes 4-8/8", b"EFGH", 4),
            ("bytes=0-0", b"", "bytes 0-0/8", b"A", 1),
            ("bytes=0-7", b"ABCDEFG", "bytes 0-7/8", b"ABCDEFGH", 8),
        ]
        for header, observed_body, observed_range, expected_body, expected_length in cases:
            with self.subTest(range=header):
                server, _ = make_server()
                with patch.object(http_module, "StreamResponse", CaptureStream):
                    response = await server._stream_handler(make_request(1, 2, header))
                self.assertEqual(response.status, 206)
                self.assertEqual(response.body, observed_body)
                self.assertEqual(response.headers["Content-Range"], observed_range)
                self.assertEqual(response.headers["Content-Length"], "8")
                self.assertTrue(response.body != expected_body or
                                int(response.headers["Content-Length"]) != expected_length)
                print(f"Observed {header}: body={response.body!r}, length=8; "
                      f"expected body={expected_body!r}, length={expected_length}.")

    async def test_suffix_and_overlong_end_are_rejected(self):
        for header in ("bytes=-3", "bytes=4-100"):
            with self.subTest(range=header):
                server, _ = make_server()
                response = await server._stream_handler(make_request(1, 2, header))
                self.assertEqual(response.status, 400)
                print(f"Observed {header}: HTTP 400; expected a satisfiable HTTP 206 response.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
