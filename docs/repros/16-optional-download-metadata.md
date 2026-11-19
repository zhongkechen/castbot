# Treat optional download metadata as optional

A downloaded video can proceed with missing or null duration, title, or dimensions. A thumbnail is passed to upload only when the generated file exists. Regression tests also cover complete metadata and a generated thumbnail.

Run the regression tests from the repository root after installing the locked dependencies.

```sh
poetry run python -m unittest discover -s tests/repro_cases -p test_16_optional_download_metadata.py -v
```
