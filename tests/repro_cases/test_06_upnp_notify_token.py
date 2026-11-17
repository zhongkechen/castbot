"""Passing tests confirm the currently observed UPnP notification defect."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from castbot.devices.upnp import DeviceStatus, UpnpNotifyServer
from castbot.utils import LocalToken


class UpnpNotifyTokenRepro(unittest.IsolatedAsyncioTestCase):
    def request_for(self, token):
        return SimpleNamespace(
            match_info={"local_token": str(token)},
            read=AsyncMock(return_value=b"<event/>"),
        )

    async def test_registered_hex_token_is_rejected_before_body_is_read(self):
        server = UpnpNotifyServer()
        token = LocalToken(123, 0xABCDEF)
        server.add_device(DeviceStatus(SimpleNamespace(reconnect=AsyncMock())), token)
        request = self.request_for(token)
        self.assertTrue(any(char in str(token) for char in "abcdef"))

        response = await server.handle(request)

        self.assertEqual(response.status, 400)
        request.read.assert_not_awaited()
        self.assertIn(token, server._devices)

    async def test_registered_digit_only_hex_token_raises_type_error(self):
        server = UpnpNotifyServer()
        token = LocalToken(0x11, 0x111)
        server.add_device(DeviceStatus(SimpleNamespace(reconnect=AsyncMock())), token)
        request = self.request_for(token)
        self.assertTrue(str(token).isdigit())

        with self.assertRaises(TypeError):
            await server.handle(request)

        request.read.assert_not_awaited()
        self.assertIn(token, server._devices)


if __name__ == "__main__":
    unittest.main()
