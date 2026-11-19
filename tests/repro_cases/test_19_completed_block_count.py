"""Check stream cleanup reports remaining blocks accurately."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from castbot.http import Http
from castbot.utils import LocalToken


class CompletedBlockCountTest(unittest.IsolatedAsyncioTestCase):
    async def remaining_after_blocks(self, size, offsets):
        token = LocalToken(123, 456)
        video = SimpleNamespace(close=AsyncMock())
        server = Http({"listen_port": 8350, "listen_host": "127.0.0.1", "block_size": 4}, None, [])
        server._tokens[token] = video
        for offset in offsets:
            server._feed_downloaded_blocks(offset, token)

        # The empty transport set represents all HTTP clients having closed.
        await server._timeout_handler(token, size)

        video.close.assert_awaited_once()
        self.assertNotIn(token, server._tokens)
        return video.close.await_args.args[0]

    async def test_complete_aligned_and_unaligned_files_report_zero_remaining(self):
        for size in (4, 8, 9):
            with self.subTest(size=size):
                self.assertEqual(await self.remaining_after_blocks(size, range(0, size, 4)), 0)

    async def test_partial_files_count_each_downloaded_block_once(self):
        self.assertEqual(await self.remaining_after_blocks(8, (0, 0)), 50.0)
        self.assertAlmostEqual(await self.remaining_after_blocks(9, (0,)), 200.0 / 3)
        self.assertEqual(await self.remaining_after_blocks(4, ()), 100.0)

    async def test_empty_file_has_no_remaining_data(self):
        self.assertEqual(await self.remaining_after_blocks(0, ()), 0)


if __name__ == "__main__":
    unittest.main()
