# Deliver STOP to the Web player

The next poll reports a pending stop once with HTTP 204. The page pauses the video and clears its source. If STOP and PLAY arrive before the same poll, the most recent command is delivered.

Run the regression tests from the repository root after installing the locked dependencies.

```sh
poetry run python -m unittest discover -s tests/repro_cases -p test_10_web_stop_command.py -v
```
