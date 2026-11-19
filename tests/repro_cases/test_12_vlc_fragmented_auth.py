"""Check VLC authentication across TCP read boundaries."""
import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import castbot.devices.vlc as vlc_module
from castbot.devices.vlc import VlcDevice, VlcDeviceParams


class RecordedWriter:
    def __init__(self):
        self.writes = []
        self.closed = False

    def write(self, data):
        self.writes.append(data)

    async def drain(self):
        pass

    def close(self):
        self.closed = True


class VlcFragmentedAuthTest(unittest.IsolatedAsyncioTestCase):
    async def stop_with_chunks(self, chunks):
        reader = SimpleNamespace(read=AsyncMock(side_effect=chunks))
        writer = RecordedWriter()
        device = VlcDevice(VlcDeviceParams({
            "host": "example.invalid", "port": 4212, "password": "repro-dummy-password",
        }))
        with patch.object(vlc_module.asyncio, "open_connection", AsyncMock(return_value=(reader, writer))):
            await device.stop()
        return reader, writer

    async def test_complete_authentication_bytes_allow_the_command(self):
        banner = b"Password: " + vlc_module._AUTH_MAGIC
        reader, writer = await self.stop_with_chunks([banner, vlc_module._AUTH_OK])
        self.assertEqual(reader.read.await_count, 2)
        self.assertEqual(writer.writes, [b"repro-dummy-password" + vlc_module._EOF,
                                         b"stop " + vlc_module._EOF])

    async def test_fragmented_banner_still_sends_password(self):
        fragments = [b"Password: ", vlc_module._AUTH_MAGIC]
        self.assertEqual(b"".join(fragments), b"Password: " + vlc_module._AUTH_MAGIC)
        reader, writer = await self.stop_with_chunks([*fragments, vlc_module._AUTH_OK])
        self.assertEqual(reader.read.await_count, 3)
        self.assertEqual(writer.writes, [b"repro-dummy-password" + vlc_module._EOF, b"stop " + vlc_module._EOF])
        self.assertTrue(writer.closed)

    async def test_fragmented_auth_success_still_sends_command(self):
        banner = b"Password: " + vlc_module._AUTH_MAGIC
        prefix, suffix = vlc_module._AUTH_OK[:3], vlc_module._AUTH_OK[3:]
        self.assertEqual(prefix + suffix, vlc_module._AUTH_OK)
        reader, writer = await self.stop_with_chunks([banner, prefix, suffix])
        self.assertEqual(reader.read.await_count, 3)
        self.assertEqual(writer.writes, [b"repro-dummy-password" + vlc_module._EOF, b"stop " + vlc_module._EOF])
        self.assertTrue(writer.closed)


    async def test_plain_tcp_greeting_sends_command_without_password(self):
        reader, writer = await self.stop_with_chunks([b"Command Line"])
        self.assertEqual(reader.read.await_count, 1)
        self.assertEqual(writer.writes, [b"stop " + vlc_module._EOF])
        self.assertTrue(writer.closed)

    async def test_truncated_password_prompt_closes_connection(self):
        reader = asyncio.StreamReader()
        reader.feed_data(b"Pass")
        reader.feed_eof()
        writer = RecordedWriter()
        device = VlcDevice(VlcDeviceParams({"host": "example.invalid", "port": 4212}))
        with patch.object(vlc_module.asyncio, "open_connection", AsyncMock(return_value=(reader, writer))):
            with self.assertRaises(ConnectionError):
                await device.stop()
        self.assertEqual(writer.writes, [])
        self.assertTrue(writer.closed)


if __name__ == "__main__":
    unittest.main()
