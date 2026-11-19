# Align the README with the command line and package metadata

The pip installation example uses the count flag -v. The documented minimum is Python 3.11, as declared by the package. The regression runs the README command through the actual argument parser with offline startup and checks the declared version.

Run the regression tests from the repository root after installing the locked dependencies.

```sh
poetry run python -m unittest discover -s tests/repro_cases -p test_20_readme_cli_mismatch.py -v
```
