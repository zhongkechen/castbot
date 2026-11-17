# [P3] Completed downloads report remaining data

A file size is exactly divisible by HTTP `block_size`, all blocks have been transferred, and the client ends its connection. Timeout cleanup calculates the total as `size // block_size + 1`, counting one nonexistent extra block.

## Expected and observed

| Downloaded file | block_size | Actual downloaded blocks | Expected remaining | Remaining passed to close |
|---|---|---|---|---|
| 4 bytes | 4 | 1 | 0% | 50% |
| 8 bytes | 4 | 2 | 0% | 33.33% |
| 9 bytes, control | 4 | 3 | 0% | 0% |

Consequently, control-message processing after a complete transfer reports that content remains undownloaded.

Source: [Block and percentage calculation](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/http.py#L197), [Control message on close](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/video.py#L224).

## Reproduce

From the repository root:

```bash
poetry install --no-root
poetry run python -m unittest discover -s tests/repro_cases -p test_19_completed_block_count.py -v
```

The case uses real Http block recording and `_timeout_handler`. It records all valid blocks for the file size, directly invokes the timeout callback with no active transport, and captures the actual percentage passed to video `close`.

**A passing test confirms that the current defect was reproduced; it does not indicate a fix.** The cases assert the observed faulty behavior. Those assertions will need to be updated or replaced when the behavior changes.

This PR adds only the problem description and reproduction case.

## Validation limits

Video `close` is an AsyncMock; no Telegram control message is sent. No real file is downloaded, no 900-second wait occurs, and no HTTP server is started. The two automated tests are independent of other reproduction PRs.
