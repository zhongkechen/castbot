# Keep credentials out of logs

Device discovery logs identify the finder class. Stream diagnostics include the method or message ID and omit request headers and tokens. The aiohttp request-line access log is disabled because Web registration and stream paths contain credentials.

Run the regression tests from the repository root after installing the locked dependencies.

```sh
poetry run python -m unittest discover -s tests/repro_cases -p test_05_sensitive_log_data.py -v
```
