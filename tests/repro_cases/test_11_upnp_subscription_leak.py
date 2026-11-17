"""Passing test confirms repeated UPnP play leaves the old subscription open."""
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


class UpnpSubscriptionLeakRepro(unittest.IsolatedAsyncioTestCase):
    async def test_replacing_and_closing_b_does_not_close_subscription_a(self):
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
            self.assertTrue(first.started)
            self.assertEqual(first.close_count, 0)
            await player.on_close(token_b)

        self.assertTrue(first.started)
        self.assertEqual(first.close_count, 0)
        self.assertFalse(second.started)
        self.assertEqual(second.close_count, 1)
        self.assertIn(token_a, notifications._devices)
        self.assertNotIn(token_b, notifications._devices)


if __name__ == "__main__":
    unittest.main()
