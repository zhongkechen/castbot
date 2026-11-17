"""Passing tests confirm finder failures currently discard healthy results."""
import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import castbot.device as device_module
from castbot.device import DeviceFinderCollection


class FinderFailureRepro(unittest.IsolatedAsyncioTestCase):
    def collection(self, failed_find, working_find):
        collection = DeviceFinderCollection.__new__(DeviceFinderCollection)
        collection._devices = []
        collection._finders = [
            SimpleNamespace(request_timeout=0, find=failed_find),
            SimpleNamespace(request_timeout=0, find=working_find),
        ]
        return collection

    async def test_real_timeout_discards_a_healthy_finder_result(self):
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
            with self.assertRaises(TimeoutError):
                await collection.refresh_all_devices()

        working.assert_awaited_once()
        self.assertEqual(requested_deadlines, [1, 1])
        self.assertEqual(collection._devices, [])

    async def test_network_failure_discards_a_healthy_finder_result(self):
        available_device = object()
        working = AsyncMock(return_value=[available_device])
        broken = AsyncMock(side_effect=ConnectionError("repro finder is unavailable"))
        collection = self.collection(broken, working)

        with self.assertRaises(ConnectionError):
            await collection.refresh_all_devices()

        working.assert_awaited_once()
        self.assertEqual(collection._devices, [])


if __name__ == "__main__":
    unittest.main()
