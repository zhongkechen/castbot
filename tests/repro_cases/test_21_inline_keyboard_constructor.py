"""Passing tests confirm positional button data is interpreted as an emoji ID."""
import unittest
from types import SimpleNamespace

from pyrogram.raw.types import KeyboardButtonCallback
from pyrogram.types import InlineKeyboardButton

from castbot.button import DeviceButton, DeviceSelectButton, PlayButton, RetryButton
from castbot.utils import LocalToken


class InlineKeyboardConstructorRepro(unittest.IsolatedAsyncioTestCase):
    def application_buttons(self):
        video = SimpleNamespace(local_token=LocalToken(123, 456))
        return [
            DeviceSelectButton("repro TV", video),
            PlayButton(video),
            DeviceButton(video),
            RetryButton(None),
        ]

    async def test_actual_application_buttons_fail_serialization_before_any_rpc(self):
        for application_button in self.application_buttons():
            with self.subTest(button=type(application_button).__name__):
                expected_data = application_button.get_data()
                actual = application_button.get_button()
                self.assertIsNone(actual.callback_data)
                self.assertEqual(actual.icon_custom_emoji_id, expected_data)
                with self.assertRaises(ValueError):
                    await actual.write(None)

    async def test_same_payload_is_serializable_as_a_callback_data_keyword(self):
        for application_button in self.application_buttons():
            with self.subTest(button=type(application_button).__name__):
                data = application_button.get_data()
                # Dependency API control only; no application implementation is patched.
                control = InlineKeyboardButton(application_button.text, callback_data=data)
                raw = await control.write(None)
                self.assertIsInstance(raw, KeyboardButtonCallback)
                self.assertEqual(raw.data, data.encode("utf-8"))


if __name__ == "__main__":
    unittest.main()
