"""Ensure healthy devices remain available during partial discovery failures."""
import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import castbot.device as device_module
from castbot.device import DeviceFinderCollection


class FinderFailureTest(unittest.IsolatedAsyncioTestCase):
    def collection(self, failed_find, working_find):
        collection = DeviceFinderCollection.__new__(DeviceFinderCollection)
        collection._devices = []
        collection._finders = [
            SimpleNamespace(request_timeout=0, find=failed_find),
            SimpleNamespace(request_timeout=0, find=working_find),
        ]
        return collection

    async def test_real_timeout_preserves_a_healthy_finder_result(self):
        available_device = object()
        working = AsyncMock(return_value=[available_device])

        async def wait_until_cancelled():
            await asyncio.Event().wait()

        slow = AsyncMock(side_effect=wait_until_cancelled)
        collection = self.collection(slow, working)
        real_timeout = device_module.async_timeout.timeout
        requested_deadlines = []

        def accelerated_timeout(deadline):
            requested_deadlines.append(deadline)
            return real_timeout(0.01)

        with patch.object(device_module.async_timeout, "timeout", accelerated_timeout):
            await collection.refresh_all_devices()

        working.assert_awaited_once()
        self.assertEqual(requested_deadlines, [1, 1])
        self.assertEqual(await collection.list_all_devices(), [available_device])

    async def test_network_failure_preserves_a_healthy_finder_result(self):
        available_device = object()
        working = AsyncMock(return_value=[available_device])
        broken = AsyncMock(side_effect=ConnectionError("repro finder is unavailable"))
        collection = self.collection(broken, working)

        await collection.refresh_all_devices()

        working.assert_awaited_once()
        self.assertEqual(await collection.list_all_devices(), [available_device])


    async def test_refresh_propagates_cancellation(self):
        started = asyncio.Event()

        async def wait_until_cancelled():
            started.set()
            await asyncio.Event().wait()

        collection = self.collection(AsyncMock(side_effect=wait_until_cancelled), AsyncMock(return_value=[]))
        refresh = asyncio.create_task(collection.refresh_all_devices())
        await started.wait()
        refresh.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await refresh


if __name__ == "__main__":
    unittest.main()
