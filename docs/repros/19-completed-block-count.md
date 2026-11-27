# Calculate remaining media bytes from the ranges served

Cleanup counts only the unique media bytes written to the player. Overlapping and repeated requests count each byte once. Complete and empty files report zero remaining.

Run the regression tests from the repository root after installing the locked dependencies.

```sh
poetry run python -m unittest discover -s tests/repro_cases -p test_19_completed_block_count.py -v
```
