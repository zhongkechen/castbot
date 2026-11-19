# Build valid Telegram callback buttons with pyroblack

Application buttons pass the payload through the callback_data keyword. The tests serialize real pyroblack buttons to MTProto and verify both the label and callback bytes for device selection, PLAY, device menu, and download retry.

Run the regression tests from the repository root after installing the locked dependencies.

```sh
poetry run python -m unittest discover -s tests/repro_cases -p test_21_inline_keyboard_constructor.py -v
```
