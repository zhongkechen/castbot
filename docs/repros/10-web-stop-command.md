# [P2] STOP sends no stop command after Web playback starts

## Problem

A Web player has already received a playback URL through polling, and the user invokes STOP.

Expected: the browser receives a distinguishable stop event and stops the current video. Observed: stop only clears the already-consumed `_url_to_play`; the next poll is indistinguishable from an ordinary no-update poll and returns 302 with an empty body. The HTML polling callback has no branch that executes a stop operation. The application requests a controller update, but sends no stop command to the browser.

The automated reproducer uses the real PlayingVideo.stop, WebDevice, and poll handler to verify this protocol behavior.

Optional manual browser check, not performed here: configure a Web device and open `/static/index.html`; sign in and start a video; while the video is playing, invoke STOP from a usable Telegram controller; observe the controller update and whether browser playback continues. Controller rendering has an independently recorded dependency-constructor defect, so the automated case isolates the Web STOP protocol from rendering.

Sources: [castbot/devices/web.py:26](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/devices/web.py#L26), [castbot/devices/web.py:99](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/devices/web.py#L99), [castbot/static/index.html:30](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/static/index.html#L30).

## Reproduction

Install this branch's locked dependencies, then run from the repository root:

```bash
poetry install --no-root
poetry run python -m unittest discover -s tests/repro_cases -p test_10_web_stop_command.py -v
```

`tests/repro_cases/test_10_web_stop_command.py` runs independently without helpers from other issue PRs. It asserts the currently observed defect: **PASS confirms reproduction, not remediation**. Update or replace these assertions when the corresponding behavior changes. This PR adds only the issue description and reproduction case; production code and CI are unchanged.

## Validation boundaries

The automated case verifies that the server protocol has no stop event. It does not execute browser HTML or real Telegram operations; controller updates are mocked. The browser behavior is covered by the optional manual steps above.
