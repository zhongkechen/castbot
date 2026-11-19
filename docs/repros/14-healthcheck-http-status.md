# Report unhealthy HTTP responses to Docker

The health-check command exits successfully on HTTP 200. Error statuses, redirects, and connection failures produce a nonzero exit code.

Run the regression tests from the repository root after installing the locked dependencies.

```sh
poetry run python -m unittest discover -s tests/repro_cases -p test_14_healthcheck_http_status.py -v
```
