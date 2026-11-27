# Keep healthy devices available during discovery failures

Each finder handles its own timeouts and errors so successful results still populate the menu. Cancelling the overall refresh propagates cancellation to its caller.

Run the regression tests from the repository root after installing the locked dependencies.

```sh
poetry run python -m unittest discover -s tests/repro_cases -p test_07_finder_failure_isolation.py -v
```
