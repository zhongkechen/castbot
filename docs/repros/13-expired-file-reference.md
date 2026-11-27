# Refresh expired Telegram file references

When a file reference expires, refresh the cached message and retry the block once using the new reference to the same document. Parallel requests reuse the refreshed cache entry. A different document or a second expiration preserves the error.

Run the regression tests from the repository root after installing the locked dependencies.

```sh
poetry run python -m unittest discover -s tests/repro_cases -p test_13_expired_file_reference.py -v
```
