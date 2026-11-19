# Scope media tokens to their message

Authorization compares the message ID and token independently. The stream route rejects values outside the unsigned 64-bit token range before requesting media. Existing packed callback tokens still round-trip.

Run the regression tests from the repository root after installing the locked dependencies.

```sh
poetry run python -m unittest discover -s tests/repro_cases -p test_02_media_token_scope.py -v
```
