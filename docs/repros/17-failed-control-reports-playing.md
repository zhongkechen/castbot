## Problem

Kodi HTTP 401 responses are converted into normal return values. VLC authentication rejection also closes the connection and returns normally. With Telegram message operations mocked as successful, the real PLAY control logic still requests a Playing message update and a success answer.

This PR adds a problem record and an independently runnable offline reproduction case. Review priority: **P2**.

## Trigger

All Kodi RPC requests return 401, or VLC telnet rejects authentication after the password is submitted.

## Expected and observed

- Expected: failed device control produces a failure result rather than selecting a playing status.
- Observed: all four Kodi RPCs return 401, and all three VLC connections reject authentication. Both cases still call the message-update mock with text beginning with Playing, and the `callback.answer` mock receives Playing.

## Source locations

- [castbot/devices/xbmc.py:88](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/devices/xbmc.py#L88)
- [castbot/devices/xbmc.py:121](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/devices/xbmc.py#L121)
- [castbot/devices/vlc.py:63](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/devices/vlc.py#L63)
- [castbot/video.py:194](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/video.py#L194)

## Reproduce

From the repository root, in an environment with the project's locked dependencies installed:

```bash
poetry run python -m unittest discover -s tests/repro_cases -p test_17_failed_control_reports_playing.py -v
```

The cases instantiate real drivers, PlayingVideo and VideoControlButton. Device network operations are replaced with a 401 HTTP session or an authentication-rejecting telnet reader/writer. Telegram message updates and callback answers are mocked as successful. The real `on_click → play → driver` chain runs, allowing the cases to inspect whether driver errors propagate and which status the caller selects.

**A passing test confirms that the current defect was reproduced; it does not indicate a fix.** The cases assert the observed faulty behavior. Those assertions will need to be updated or replaced when the behavior changes.

## Validation and limits

Local offline execution with Python 3.14: **2 tests passed**.

- No real Kodi/VLC instance or device password is used.
- The cases cover HTTP 401 and complete authentication rejection. TCP fragmentation is not tested here and has a separate reproduction case.
- No Telegram message serialization or transmission occurs. The separate button-construction defect, finding 21, currently blocks real message transmission first. These cases isolate the message boundary to reproduce the independent failure to propagate driver errors; they do not claim that a real Telegram user received Playing.
