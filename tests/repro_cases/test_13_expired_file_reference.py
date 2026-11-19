"""Verify Telegram file references refresh during streamed playback."""

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from pyrogram.errors import FileReferenceExpired
from pyrogram.raw.types import Document, Message, MessageMediaDocument, PeerUser

from pyrogram.raw.types.storage.file_unknown import FileUnknown
from pyrogram.raw.types.upload import File

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


class ExpiredReferenceTest(unittest.IsolatedAsyncioTestCase):
    def make_client(self, messages, get_file):
        client = BotClient.__new__(BotClient)
        client._client = SimpleNamespace(
            invoke=AsyncMock(side_effect=[SimpleNamespace(messages=[message]) for message in messages]),
            media_sessions={4: SimpleNamespace(invoke=AsyncMock(side_effect=get_file))},
        )
        client._file_fake_fw_wait = 0
        client.get_message.cache_clear()
        self.addCleanup(client.get_message.cache_clear)
        return client

    async def test_expired_reference_refreshes_for_parallel_reads_and_replay(self):
        references = []
        old = media_message(b"old")
        new = media_message(b"new")

        async def get_file(request, **_kwargs):
            reference = request.location.file_reference
            references.append((request.offset, reference))
            if reference == b"old":
                await asyncio.sleep(0)
                raise FileReferenceExpired()
            return File(type=FileUnknown(), mtime=0, bytes=b"data")

        client = self.make_client([old, new], get_file)
        cached = await client.get_message(123)
        self.assertIs(cached, old)
        blocks = await asyncio.gather(client.get_block(cached, 0, 4), client.get_block(cached, 4, 4))
        self.assertEqual(blocks, [b"data", b"data"])
        self.assertEqual(await client.get_block(cached, 8, 4), b"data")
        self.assertIs(await client.get_message(123), new)
        self.assertEqual(client._client.invoke.await_count, 2)
        self.assertCountEqual(references, [(0, b"old"), (4, b"old"), (0, b"new"), (4, b"new"), (8, b"new")])

    async def test_still_expired_reference_propagates_after_one_retry(self):
        client = self.make_client([media_message(b"old"), media_message(b"new")], FileReferenceExpired())
        with self.assertRaises(FileReferenceExpired):
            await client.get_block(await client.get_message(123), 0, 4)
        self.assertEqual(client._client.invoke.await_count, 2)
        self.assertEqual(client._client.media_sessions[4].invoke.await_count, 2)

    async def test_changed_document_is_not_used_for_the_existing_stream(self):
        edited = media_message(b"new")
        edited.media.document.id = 999
        client = self.make_client([media_message(b"old"), edited], FileReferenceExpired())
        with self.assertRaises(FileReferenceExpired):
            await client.get_block(await client.get_message(123), 0, 4)
        self.assertEqual(client._client.invoke.await_count, 2)
        self.assertEqual(client._client.media_sessions[4].invoke.await_count, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
