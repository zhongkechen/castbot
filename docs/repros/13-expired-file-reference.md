## Problem

The get_message cache has no TTL and retains an old Telegram file reference. A FileReferenceExpired error from file retrieval does not cause the message to be fetched again; replaying the same video reuses the old reference and fails again.

This PR adds an issue description and an independently executable offline reproduction case, with review priority **P2**.

## Preconditions

A video message has been cached. The mocked Telegram file RPC returns the real FileReferenceExpired exception type on subsequent reads. A successful message response with a fresh reference is prepared as the next fetch response.

## Expected and observed behavior

- Expected: after a file reference expires, replay should not continue reusing that invalid reference.
- Observed: both replay attempts raise FileReferenceExpired, and both file requests contain the old reference. GetMessages runs only once; the prepared fresh reference is never fetched.

## Source locations

- [castbot/client.py:51](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/client.py#L51)
- [castbot/client.py:83](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/client.py#L83)
- [castbot/client.py:92](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/client.py#L92)

## Reproduction

From the repository root, in an environment with the project's locked dependencies installed, run:

```bash
poetry run python -m unittest discover -s tests/repro_cases -p test_13_expired_file_reference.py -v
```

The case constructs real RawMessage and Document objects and replaces Telegram RPCs with local AsyncMock objects. It executes the real get_message → get_block sequence twice and checks caching, request references, and RPC call counts.

**PASS confirms the currently observed defect, not remediation.** The case asserts existing erroneous behavior; update or replace these assertions when that behavior changes.

## Validation and limitations

Offline Python 3.14 verification: **1 test passed**.

- No Telegram connection was made, and the server's actual reference-expiration interval was not measured.
- The RPC boundary simulates a known file-reference-expiration error. All document identifiers, references, and account data are fictional.
