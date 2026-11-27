"""Verify that UPnP subscriptions belong to the active playback token."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from castbot.devices.upnp import UpnpDevice, UpnpNotifyServer
from castbot.utils import LocalToken


class RecordedSubscription:
    def __init__(self, device, service, url):
        self.url = url
        self.started = False
        self.close_count = 0

    async def start(self):
        self.started = True

    async def close(self):
        self.close_count += 1
        self.started = False


class UpnpSubscriptionTest(unittest.IsolatedAsyncioTestCase):
    async def test_replacing_playback_closes_previous_subscription_and_ignores_stale_cleanup(self):
        action = SimpleNamespace(async_call=AsyncMock())
        service = SimpleNamespace(action=lambda _name: action)
        device = SimpleNamespace(service=lambda _schema: service, friendly_name="repro TV")
        notifications = UpnpNotifyServer()
        player = UpnpDevice(device, notifications)
        token_a, token_b = LocalToken(101, 1), LocalToken(102, 2)
        subscriptions = []

        def subscription_factory(*args):
            subscription = RecordedSubscription(*args)
            subscriptions.append(subscription)
            return subscription

        with patch("castbot.devices.upnp.SubscribeTask", subscription_factory):
            await player.play("http://example.invalid/stream/101/1", "A", token_a)
            await player.play("http://example.invalid/stream/102/2", "B", token_b)
            self.assertEqual(len(subscriptions), 2)
            first, second = subscriptions
            self.assertIs(player._subscribe_task, second)
            self.assertFalse(first.started)
            self.assertEqual(first.close_count, 1)
            self.assertNotIn(token_a, notifications._devices)
            self.assertIn(token_b, notifications._devices)
            await player.on_close(token_a)
            self.assertTrue(second.started)
            self.assertEqual(second.close_count, 0)
            await player.on_close(token_b)
            await player.on_close(token_b)

        self.assertFalse(first.started)
        self.assertEqual(first.close_count, 1)
        self.assertFalse(second.started)
        self.assertEqual(second.close_count, 1)
        self.assertNotIn(token_a, notifications._devices)
        self.assertNotIn(token_b, notifications._devices)

    async def test_failed_play_closes_subscription_and_removes_notification(self):
        actions = {
            "SetAVTransportURI": SimpleNamespace(async_call=AsyncMock()),
            "Play": SimpleNamespace(async_call=AsyncMock(side_effect=ConnectionError)),
        }
        service = SimpleNamespace(action=actions.__getitem__)
        device = SimpleNamespace(service=lambda _schema: service, friendly_name="test TV")
        notifications = UpnpNotifyServer()
        player = UpnpDevice(device, notifications)
        token = LocalToken(101, 1)
        subscription = RecordedSubscription(device, service, "http://example.invalid")
        with patch("castbot.devices.upnp.SubscribeTask", return_value=subscription):
            with self.assertRaises(ConnectionError):
                await player.play("http://example.invalid/stream/101/1", "A", token)

        self.assertEqual(subscription.close_count, 1)
        self.assertIsNone(player._subscribe_task)
        self.assertNotIn(token, notifications._devices)


if __name__ == "__main__":
    unittest.main()
