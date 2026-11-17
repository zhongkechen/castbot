# [P2] Stale playback cleanup unregisters the device used by active playback

## Problem

A user plays A and then B on the same selected device. After A's connections end, A's cleanup can still run when its default 900-second grace period expires.

Expected: A's cleanup releases A's resources while B and its device remain valid. Observed: A.close calls on_close on the shared device, and WebDevice unconditionally unregisters that browser. B remains in the application's playback map and the HTTP token map but loses the Web device registration.

The reproducer uses real Http, PlayingVideos, and WebDevice instances. A and B inherit the same user-selected device; B has a transport reporting active, and its playback URL has already been consumed. Invoking A's real HTTP timeout callback unregisters the browser while B remains active. This case records cleanup ownership separately from the repeated-UPnP-subscription issue.

Sources: [castbot/http.py:205](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/http.py#L205), [castbot/video.py:224](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/video.py#L224), [castbot/devices/web.py:29](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/devices/web.py#L29), [castbot/devices/chromecast.py:33](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/devices/chromecast.py#L33), [castbot/devices/upnp.py:233](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/devices/upnp.py#L233).

## Reproduction

Install this branch's locked dependencies, then run from the repository root:

```bash
poetry install --no-root
poetry run python -m unittest discover -s tests/repro_cases -p test_09_stale_playback_cleanup.py -v
```

`tests/repro_cases/test_09_stale_playback_cleanup.py` runs independently without helpers from other issue PRs. It asserts the currently observed defect: **PASS confirms reproduction, not remediation**. Update or replace these assertions when the corresponding behavior changes. This PR adds only the issue description and reproduction case; production code and CI are unchanged.

## Validation boundaries

The expired callback is invoked directly rather than waiting 900 seconds. Telegram controller updates and transports are test doubles. The automated case exercises the Web driver without connecting to a browser, Chromecast, or UPnP device.
