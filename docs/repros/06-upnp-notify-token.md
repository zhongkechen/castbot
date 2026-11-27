# Accept registered hexadecimal UPnP notification tokens

The notification endpoint parses the hexadecimal token emitted in the callback URL. The regression checks both letter-containing and digit-only tokens, verifies a playback status update, and checks that malformed and unknown tokens are rejected before reading the body.

Run the regression tests from the repository root after installing the locked dependencies.

```sh
poetry run python -m unittest discover -s tests/repro_cases -p test_06_upnp_notify_token.py -v
```
