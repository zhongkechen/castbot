# Keep active Web playback registered during stale stream cleanup

A Web player tracks the token that owns its current playback. An earlier stream can finish its own cleanup without removing the browser registration. Cleanup for the current playback still releases the registration.

Run the regression tests from the repository root after installing the locked dependencies.

```sh
poetry run python -m unittest discover -s tests/repro_cases -p test_09_stale_playback_cleanup.py -v
```
