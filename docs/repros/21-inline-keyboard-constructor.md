# [P1] Inline keyboard construction fails with locked pyroblack

The locked pyroblack 3.0.5 API defines the second positional argument of InlineKeyboardButton as `icon_custom_emoji_id`, while `callback_data` is keyword-only. Application `Button.get_button` still passes the intended callback payload as the second positional argument.

Expected: device-selection, PLAY, device-menu and retry buttons contain `callback_data` and serialize as Telegram callback buttons. Observed: `callback_data` is None, and the payload is stored as `icon_custom_emoji_id`. Serialization calls `int(icon_custom_emoji_id)`, raising ValueError for payloads such as `c:...:PLAY` and `s:...:repro TV`. The failure precedes any Telegram RPC and prevents normal control-message sending or updating.

Source: [button.py:38](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/button.py#L38), [pyproject.toml:22](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/pyproject.toml#L22).

## Reproduce

After installing the locked dependencies, run from the repository root:

```bash
poetry install --no-root
poetry run python -m unittest discover -s tests/repro_cases -p test_21_inline_keyboard_constructor.py -v
```

The cases use `get_button` on four real application buttons and invoke the dependency's real `write(None)` to check construction fields and serialization failure. As a control, the same payload is serialized normally by constructing a dependency object with the supported `callback_data` keyword. This control creates an object only within the test; the application implementation is neither modified nor patched.

**A passing test confirms that the current defect was reproduced; it does not indicate a fix.** The cases assert the observed faulty behavior. Those assertions will need to be updated or replaced when the behavior changes.

This PR contains only a problem description and an independent reproduction file. Production code and CI are unchanged.

## Validation limits

The cases use dummy LocalToken values and button labels. In the tested callback branch, `write(None)` does not access a client. No network, real Telegram users or credentials are used. The dependency API control verifies that the same payload is valid; no real control-message RPC is sent.
