## Problem

The bot registers a `video_note` handler, but `pyrogram_filename` accesses `VideoNote.file_name`. A real VideoNote has no such attribute. `play` handles TypeError only, so an AttributeError occurs before any device playback command.

This PR adds a problem record and an independently runnable offline reproduction case. Review priority: **P2**.

## Trigger

Select a device, then execute `PlayingVideo.play` with a real `pyrogram.types.VideoNote` object.

## Expected and observed

- Expected: a circular video can enter device playback; the absence of a filename does not block playback.
- Observed: an AttributeError mentioning `file_name` is raised. Device stop/play commands and the playback status update are not executed.

## Source locations

- [castbot/bot.py:34](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/bot.py#L34)
- [castbot/video.py:188](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/video.py#L188)
- [castbot/video.py:237](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/video.py#L237)

## Reproduce

From the repository root, in an environment with the project's locked dependencies installed:

```bash
poetry run python -m unittest discover -s tests/repro_cases -p test_15_video_note_filename.py -v
```

The case creates a real VideoNote, a real PlayingVideo and a dummy token. Only external device and control-message operations are mocked. It executes the real `play` method and checks the exception and the absence of playback commands.

**A passing test confirms that the current defect was reproduced; it does not indicate a fix.** The cases assert the observed faulty behavior. Those assertions will need to be updated or replaced when the behavior changes.

## Validation and limits

Local offline execution with Python 3.14: **1 test passed**.

- No real Telegram video is sent or received, and no playback device is contacted.
- The case checks the failure at the playback entry point. It does not simulate codec or media-format compatibility.
