# [P2] Repeated UPnP playback leaves the old subscription open

## Problem

Call play(A), then play(B), on the same UpnpDevice and close B.

Expected: replacing playback releases the old subscription, and closing playback leaves no subscription belonging to the old playback. Observed: the new subscription overwrites `_subscribe_task`, A never receives close, and on_close can only close B. The real SubscribeTask implementation repeats unsubscribe/subscribe operations every 10 seconds while an unclosed task remains alive; the old notification registration also remains.

The reproducer executes real UpnpDevice.play/on_close and substitutes network calls and SubscribeTask with lifecycle-recording objects. Both subscriptions start; the second is closed once, while the first remains started with a close count of zero.

Sources: [castbot/devices/upnp.py:205](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/devices/upnp.py#L205), [castbot/devices/upnp.py:246](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/devices/upnp.py#L246), [castbot/devices/upnp.py:233](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/devices/upnp.py#L233).

## Reproduction

Install this branch's locked dependencies, then run from the repository root:

```bash
poetry install --no-root
poetry run python -m unittest discover -s tests/repro_cases -p test_11_upnp_subscription_leak.py -v
```

`tests/repro_cases/test_11_upnp_subscription_leak.py` runs independently without helpers from other issue PRs. It asserts the currently observed defect: **PASS confirms reproduction, not remediation**. Update or replace these assertions when the corresponding behavior changes. This PR adds only the issue description and reproduction case; production code and CI are unchanged.

## Validation boundaries

SubscribeTask is replaced with a lifecycle-recording test double; no real background loop or network access is started. The automated case proves that the old object is not closed. The 10-second loop is established by the original implementation, not by observing real device traffic.
