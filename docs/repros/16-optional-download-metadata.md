## Problem

The downloader unconditionally applies `int()` to `duration` and assigns the fixed `video1.jpg` thumbnail path. An absent duration causes `int(None)`. If no thumbnail was generated, a nonexistent path is still passed to subsequent upload processing.

This PR adds a problem record and an independently runnable offline reproduction case. Review priority: **P2**.

## Trigger

The download process succeeds and produces video and `info.json` files, but `duration` is null or the thumbnail is absent. `TMPDIR` must point to a writable directory.

## Expected and observed

- Expected: missing optional metadata does not invalidate a successfully downloaded video, and an upload does not receive a nonexistent thumbnail path.
- Observed: the first case raises TypeError mentioning NoneType after a successful download. The second confirms that the video exists while `DownloadedVideo.thumbnail_filename` refers to a nonexistent file.

## Source locations

- [castbot/downloader.py:71](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/downloader.py#L71)
- [castbot/downloader.py:78](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/downloader.py#L78)
- [castbot/downloader.py:123](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/downloader.py#L123)

## Reproduce

From the repository root, in an environment with the project's locked dependencies installed:

```bash
poetry run python -m unittest discover -s tests/repro_cases -p test_16_optional_download_metadata.py -v
```

The cases create actual placeholder video and JSON files under `TMPDIR`. Only subprocess creation is replaced with a successful local fake process. They then call the real `Downloader.download` and check the missing-duration and missing-thumbnail results separately.

**A passing test confirms that the current defect was reproduced; it does not indicate a fix.** The cases assert the observed faulty behavior. Those assertions will need to be updated or replaced when the behavior changes.

## Validation and limits

Local offline execution with Python 3.14: **2 tests passed**.

- The placeholder does not contain playable video. The tests focus on output files and metadata consumption.
- No yt-dlp execution, network download or Telegram upload occurs. The thumbnail case checks the nonexistent output path supplied to subsequent processing.
