# Release replaced UPnP subscriptions

Each subscription belongs to a playback token. Replacing playback closes the old subscription and removes its notification registration. Stale cleanup leaves the current subscription alone, and a failed PLAY releases its subscription.

Run the regression tests from the repository root after installing the locked dependencies.

```sh
poetry run python -m unittest discover -s tests/repro_cases -p test_11_upnp_subscription_leak.py -v
```
