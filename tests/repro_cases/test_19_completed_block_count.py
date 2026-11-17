"""Passing tests confirm complete block-aligned downloads report bytes remaining."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from castbot.http import Http
from castbot.utils import LocalToken


class CompletedBlockCountRepro(unittest.IsolatedAsyncioTestCase):
    async def remaining_after_all_blocks(self, size):
        token = LocalToken(123, 456)
        video = SimpleNamespace(close=AsyncMock())
        server = Http({"listen_port": 8350, "listen_host": "127.0.0.1", "block_size": 4}, None, [])
        server._tokens[token] = video
        for offset in range(0, size, 4):
            server._feed_downloaded_blocks(offset, token)
        self.assertEqual(len(server._downloaded_blocks[token]), (size + 3) // 4)

        # The empty transport set represents all HTTP clients having closed.
        await server._timeout_handler(token, size)

        video.close.assert_awaited_once()
        self.assertNotIn(token, server._tokens)
        return video.close.await_args.args[0]

    async def test_fully_downloaded_aligned_files_report_nonzero_remaining(self):
        for size, expected in [(4, 50.0), (8, 100.0 / 3)]:
            with self.subTest(size=size):
                remaining = await self.remaining_after_all_blocks(size)
                self.assertAlmostEqual(remaining, expected)
                self.assertGreater(remaining, 0)

    async def test_non_aligned_complete_file_reports_zero_as_a_control(self):
        self.assertEqual(await self.remaining_after_all_blocks(9), 0)


if __name__ == "__main__":
    unittest.main()
