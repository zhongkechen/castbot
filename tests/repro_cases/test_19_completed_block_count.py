"""Check stream cleanup reports remaining bytes accurately."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from castbot.http import Http
from castbot.utils import LocalToken


class CompletedBlockCountTest(unittest.IsolatedAsyncioTestCase):
    async def remaining_after_ranges(self, size, ranges):
        token = LocalToken(123, 456)
        video = SimpleNamespace(close=AsyncMock())
        server = Http({"listen_port": 8350, "listen_host": "127.0.0.1", "block_size": 4}, None, [])
        server._tokens[token] = video
        for start, stop in ranges:
            server._feed_downloaded_range(token, start, stop)

        # The empty transport set represents all HTTP clients having closed.
        await server._timeout_handler(token, size)

        video.close.assert_awaited_once()
        self.assertNotIn(token, server._tokens)
        self.assertNotIn(token, server._downloaded_ranges)
        return video.close.await_args.args[0]

    async def test_complete_aligned_and_unaligned_files_report_zero_remaining(self):
        for size in (4, 8, 9):
            with self.subTest(size=size):
                ranges = [(offset, min(offset + 4, size)) for offset in range(0, size, 4)]
                self.assertEqual(await self.remaining_after_ranges(size, ranges), 0)

    async def test_partial_transfers_count_only_unique_bytes(self):
        self.assertEqual(await self.remaining_after_ranges(4, [(0, 1)]), 75.0)
        self.assertEqual(await self.remaining_after_ranges(8, [(4, 6), (0, 2), (1, 5), (4, 6)]), 25.0)
        self.assertAlmostEqual(await self.remaining_after_ranges(9, [(0, 4)]), 500.0 / 9)
        self.assertEqual(await self.remaining_after_ranges(4, []), 100.0)

    async def test_empty_file_has_no_remaining_data(self):
        self.assertEqual(await self.remaining_after_ranges(0, []), 0)


if __name__ == "__main__":
    unittest.main()
