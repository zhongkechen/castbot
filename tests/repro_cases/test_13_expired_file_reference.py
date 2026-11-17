"""A passing case confirms the current expired-reference defect; it is not a fix."""

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from pyrogram.errors import FileReferenceExpired
from pyrogram.raw.types import Document, Message, MessageMediaDocument, PeerUser

from castbot.client import BotClient


def media_message(reference):
    document = Document(
        id=10,
        access_hash=20,
        file_reference=reference,
        date=0,
        mime_type="video/mp4",
        size=4,
        dc_id=4,
        attributes=[],
    )
    return Message(
        id=123,
        peer_id=PeerUser(user_id=99),
        date=0,
        message="",
        media=MessageMediaDocument(document=document),
    )


class ExpiredReferenceReproduction(unittest.IsolatedAsyncioTestCase):
    async def test_expired_reference_is_reused_without_refetch(self):
        old_message = media_message(b"expired-test-reference")
        refreshed_message = media_message(b"fresh-test-reference")
        message_rpc = AsyncMock(
            side_effect=[
                SimpleNamespace(messages=[old_message]),
                SimpleNamespace(messages=[refreshed_message]),
            ]
        )
        media_rpc = AsyncMock(side_effect=FileReferenceExpired())
        client = BotClient.__new__(BotClient)
        client._client = SimpleNamespace(
            invoke=message_rpc,
            media_sessions={4: SimpleNamespace(invoke=media_rpc)},
        )
        client._file_fake_fw_wait = 0
        client.get_message.cache_clear()
        self.addCleanup(client.get_message.cache_clear)

        for _ in range(2):
            message = await client.get_message(123)
            self.assertIs(message, old_message)
            with self.assertRaises(FileReferenceExpired):
                await client.get_block(message, 0, 4)

        self.assertEqual(message_rpc.await_count, 1)
        self.assertEqual(media_rpc.await_count, 2)
        for call in media_rpc.await_args_list:
            self.assertEqual(call.args[0].location.file_reference, b"expired-test-reference")
        print("Observed: two replay attempts reuse the expired reference; fresh metadata is never fetched.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
