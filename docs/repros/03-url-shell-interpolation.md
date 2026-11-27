# Pass download URLs as a single argument

The yt-dlp and you-get backends both launch directly with an argument vector. The regression verifies that the URL query, output path, and format selector reach the process boundary as individual arguments.

Run the regression tests from the repository root after installing the locked dependencies.

```sh
poetry run python -m unittest discover -s tests/repro_cases -p test_03_url_shell_interpolation.py -v
```
