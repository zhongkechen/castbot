# Play circular Telegram videos without filenames

Telegram VideoNote objects have no file_name attribute. Castbot gives them a fallback MP4 title and sends them through the normal playback flow. Named media keep their filenames.

Run the regression tests from the repository root after installing the locked dependencies.

```sh
poetry run python -m unittest discover -s tests/repro_cases -p test_15_video_note_filename.py -v
```
