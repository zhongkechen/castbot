# Keep active Web playback registered during stale stream cleanup

A Web player tracks the token that owns its current playback. Cleanup stops the current playback and keeps the browser registered for future videos. Older streams leave the current playback alone.

Run the regression tests from the repository root after installing the locked dependencies.

```sh
poetry run python -m unittest discover -s tests/repro_cases -p test_09_stale_playback_cleanup.py -v
```
