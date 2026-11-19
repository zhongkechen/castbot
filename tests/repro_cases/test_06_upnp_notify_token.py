"""Verify registered UPnP notification URLs."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from castbot.devices.upnp import DeviceStatus, UpnpNotifyServer
from castbot.utils import LocalToken


class UpnpNotifyTokenTest(unittest.IsolatedAsyncioTestCase):
    def request_for(self, token):
        return SimpleNamespace(
            match_info={"local_token": str(token)},
            read=AsyncMock(return_value=(
                b'<Event xmlns="urn:schemas-upnp-org:metadata-1-0/AVT/">'
                b'<TransportStatus val="OK"/></Event>'
            )),
        )

    async def test_registered_hex_tokens_update_playback_state(self):
        for token in (LocalToken(123, 0xABCDEF), LocalToken(0x11, 0x111)):
            with self.subTest(token=str(token)):
                server = UpnpNotifyServer()
                device_status = DeviceStatus(SimpleNamespace(reconnect=AsyncMock()))
                server.add_device(device_status, token)
                request = self.request_for(token)

                response = await server.handle(request)

                self.assertEqual(response.status, 200)
                request.read.assert_awaited_once_with()
                self.assertTrue(device_status.playing)

    async def test_invalid_or_unregistered_tokens_are_rejected_before_reading(self):
        server = UpnpNotifyServer()
        for token, expected in (("no-token", 400), ("+a", 400), ("abc", 403)):
            with self.subTest(token=token):
                request = self.request_for(token)
                response = await server.handle(request)
                self.assertEqual(response.status, expected)
                request.read.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
