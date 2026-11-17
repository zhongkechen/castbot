# [P2] Valid TCP fragmentation breaks VLC authentication

## Problem

VLC Telnet requires password authentication, and a valid authentication prompt or success reply arrives in two TCP reads. TCP read does not guarantee a complete protocol message in one call.

Expected: the same valid authentication byte stream is handled consistently across chunk boundaries, allowing the password and subsequent stop command. Observed: if the first banner chunk does not end in the authentication magic, the application skips the password and sends stop immediately. If only the first part of the success reply is read, the application treats authentication as failed and closes the connection.

The reproducer uses the implementation's actual `_AUTH_MAGIC` and `_AUTH_OK`. A complete-input control confirms that the password and stop command are sent. The same valid byte sequences are then fragmented, demonstrating an unread chunk and incorrect authentication handling.

Sources: [castbot/devices/vlc.py:54](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/devices/vlc.py#L54), [castbot/devices/vlc.py:61](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/devices/vlc.py#L61).

## Reproduction

Install this branch's locked dependencies, then run from the repository root:

```bash
poetry install --no-root
poetry run python -m unittest discover -s tests/repro_cases -p test_12_vlc_fragmented_auth.py -v
```

`tests/repro_cases/test_12_vlc_fragmented_auth.py` runs independently without helpers from other issue PRs. It asserts the currently observed defects: **PASS confirms reproduction, not remediation**. Update or replace these assertions when the corresponding behavior changes. This PR adds only the issue description and reproduction case; production code and CI are unchanged.

## Validation boundaries

asyncio.open_connection and read chunks are mocked; the case does not connect to VLC. Input contains the same valid byte stream as the control; only TCP chunk boundaries change.
