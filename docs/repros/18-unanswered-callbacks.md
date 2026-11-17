## Problem

The successful device-menu, device-selection and download-retry paths do not call `callback_query.answer`. The Telegram client continues waiting for the button callback answer.

This PR adds a problem record and an independently runnable offline reproduction case. Review priority: **P3**.

## Trigger

DEVICE/REFRESH successfully displays a menu, device selection succeeds, or a download retry completes successfully.

## Expected and observed

- Expected: these successful operations answer the callback promptly rather than waiting for client timeout.
- Observed: three cases verify that the relevant business actions complete successfully, but `callback.answer` is never awaited. The menu case covers both DEVICE and REFRESH.

## Source locations

- [castbot/button.py:123](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/button.py#L123)
- [castbot/button.py:152](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/button.py#L152)
- [castbot/button.py:177](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/button.py#L177)

## Reproduce

From the repository root, in an environment with the project's locked dependencies installed:

```bash
poetry run python -m unittest discover -s tests/repro_cases -p test_18_unanswered_callbacks.py -v
```

The cases execute the three real Button `on_click` methods. AsyncMock provides successful business responses and records `answer` calls. Each case checks that the business action finished while the answer was not executed.

**A passing test confirms that the current defect was reproduced; it does not indicate a fix.** The cases assert the observed faulty behavior. Those assertions will need to be updated or replaced when the behavior changes.

## Validation and limits

Local offline execution with Python 3.14: **3 tests passed**.

- No Telegram connection is made. The client spinner is not observed and the client timeout is not measured.
- These cases check missing answers on successful paths, rather than error-message handling on failed paths.
