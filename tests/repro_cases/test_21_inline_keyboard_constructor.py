"""Verify application buttons serialize using Telegram callback data."""
import unittest
from types import SimpleNamespace

from pyrogram.raw.types import KeyboardButtonCallback

from castbot.button import DeviceButton, DeviceSelectButton, PlayButton, RetryButton
from castbot.utils import LocalToken


class InlineKeyboardConstructorTest(unittest.IsolatedAsyncioTestCase):
    def application_buttons(self):
        video = SimpleNamespace(local_token=LocalToken(123, 456), playing_device=None)
        return [
            DeviceSelectButton("repro TV", video),
            PlayButton(video),
            DeviceButton(video),
            RetryButton(None),
        ]

    async def test_application_buttons_serialize_as_callbacks(self):
        for application_button in self.application_buttons():
            with self.subTest(button=type(application_button).__name__):
                expected_data = application_button.get_data()
                actual = application_button.get_button()
                self.assertEqual(actual.callback_data, expected_data)
                self.assertIsNone(actual.icon_custom_emoji_id)
                raw = await actual.write(None)
                self.assertIsInstance(raw, KeyboardButtonCallback)
                self.assertEqual(raw.text, application_button.text)
                self.assertEqual(raw.data, expected_data.encode("utf-8"))


if __name__ == "__main__":
    unittest.main()
