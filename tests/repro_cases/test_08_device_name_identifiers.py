"""Passing tests confirm the current device-name callback limitations."""
import unittest
from types import SimpleNamespace

from castbot.button import DeviceSelectButton, parse_data
from castbot.device import Device, DeviceFinderCollection
from castbot.utils import LocalToken
from castbot.video import PlayingVideo


class NamedDevice(Device):
    def __init__(self, name):
        self.name = name

    def get_device_name(self):
        return self.name

    async def play(self, url, title, local_token):
        pass

    async def stop(self):
        pass

    async def on_close(self, local_token):
        pass


class DeviceNameRepro(unittest.IsolatedAsyncioTestCase):
    def selection_button(self, name):
        video = SimpleNamespace(local_token=LocalToken(123, 0xABCDEF))
        return DeviceSelectButton(name, video)

    def test_normal_name_round_trips_but_colon_name_does_not(self):
        normal = self.selection_button("Living Room TV")
        self.assertEqual(parse_data(normal.get_data())[2], "Living Room TV")
        ambiguous = self.selection_button("TV:Living Room")
        with self.assertRaises(ValueError):
            parse_data(ambiguous.get_data())

    def test_unicode_name_exceeds_telegram_callback_limit(self):
        name = "电视机" * 8
        button = self.selection_button(name)
        self.assertEqual(button.text, name)
        self.assertEqual(len(button.get_data().encode("utf-8")), 93)
        self.assertGreater(len(button.get_data().encode("utf-8")), 64)

    async def test_two_same_name_devices_always_resolve_to_the_first(self):
        first = NamedDevice("Living Room TV")
        second = NamedDevice("Living Room TV")
        collection = DeviceFinderCollection.__new__(DeviceFinderCollection)
        collection._devices = [first, second]
        collection._finders = []
        self.assertIsNot(first, second)
        self.assertEqual(self.selection_button(repr(first)).get_data(),
                         self.selection_button(repr(second)).get_data())
        self.assertIs(await collection.find_device_by_name(repr(second)), first)

    def test_comma_name_is_truncated_when_restoring_a_controller(self):
        name = "TV, Living Room"
        text = f"Playing for file 123 on device {name}"
        self.assertEqual(PlayingVideo.parse_device_str(text), "TV")
        self.assertNotEqual(PlayingVideo.parse_device_str(text), name)


if __name__ == "__main__":
    unittest.main()
