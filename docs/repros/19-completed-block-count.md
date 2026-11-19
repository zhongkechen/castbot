# Calculate remaining download blocks without an extra block

Cleanup counts a trailing block only when the media has remaining bytes beyond the last block boundary. Complete and empty files report zero remaining. Partial transfers count each downloaded block once.

Run the regression tests from the repository root after installing the locked dependencies.

```sh
poetry run python -m unittest discover -s tests/repro_cases -p test_19_completed_block_count.py -v
```
