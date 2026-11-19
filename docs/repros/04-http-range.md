# Serve HTTP byte ranges with exact response lengths

A satisfiable GET range returns the inclusive requested bytes and matching response headers. Suffix ranges, ranges ending past the last byte, full responses, HEAD requests, and invalid or unsatisfiable ranges are covered with offline media fixtures.

Run the regression tests from the repository root after installing the locked dependencies.

```sh
poetry run python -m unittest discover -s tests/repro_cases -p test_04_http_range.py -v
```
