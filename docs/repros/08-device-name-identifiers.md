# Use stable device identifiers in Telegram callbacks

The keyboard keeps the full display name while routing through a compact identifier derived from the device backend and endpoint or device identity. Control and menu callbacks carry that identifier across bot restarts. Legacy buttons still accept the supported name formats. A Web player must register again after a bot restart.

Run the regression tests from the repository root after installing the locked dependencies.

```sh
poetry run python -m unittest discover -s tests/repro_cases -p test_08_device_name_identifiers.py -v
```
