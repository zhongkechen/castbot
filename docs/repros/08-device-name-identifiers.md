# [P2] Device display names break callback parsing and identity

## Problem

A device name can contain a colon, a comma, a long CJK label, or match another device's display name. The application uses that display name in callback payloads and device lookup.

Expected: each device can be selected accurately and retain its identity when a controller is restored. Observed:

- `TV:Living Room` is interpreted as the old callback format and raises ValueError.
- Eight repeats of the three-character CJK label `\u7535\u89c6\u673a` produce a 93-byte payload, exceeding Telegram's 64-byte callback_data limit.
- Two devices with the same display name produce identical intended payloads; lookup always returns the first device.
- `TV, Living Room` is restored as `TV` because the controller text parser stops at the comma.

The reproducer calls the real DeviceSelectButton.get_data(), callback parser, device lookup, and controller text parser.

Sources: [castbot/button.py:139](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/button.py#L139), [castbot/button.py:221](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/button.py#L221), [castbot/device.py:118](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/device.py#L118), [castbot/video.py:129](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/video.py#L129).

## Reproduction

Install this branch's locked dependencies, then run from the repository root:

```bash
poetry install --no-root
poetry run python -m unittest discover -s tests/repro_cases -p test_08_device_name_identifiers.py -v
```

`tests/repro_cases/test_08_device_name_identifiers.py` runs independently without helpers from other issue PRs. It asserts the currently observed defects: **PASS confirms reproduction, not remediation**. Update or replace these assertions when the corresponding behavior changes. This PR adds only the issue description and reproduction case; production code and CI are unchanged.

## Validation boundaries

The current dependency version also has an independent positional-argument defect in get_button. This case directly inspects the intended callback payload and does not claim that an actual menu send first fails because of name encoding. No oversized callback was submitted to Telegram; the test checks the generated UTF-8 byte count against the existing 64-byte protocol limit. Name lookup and restoration parsing run offline.
