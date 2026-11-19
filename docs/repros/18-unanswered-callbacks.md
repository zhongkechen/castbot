# Acknowledge device actions and download retries

Device menu and refresh, valid device selection, and download retries acknowledge the Telegram callback before menu updates, controller edits, or download work. Invalid device and link requests still receive their specific error answers.

Run the regression tests from the repository root after installing the locked dependencies.

```sh
poetry run python -m unittest discover -s tests/repro_cases -p test_18_unanswered_callbacks.py -v
```
