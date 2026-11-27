# Report device failures when PLAY cannot start

Kodi HTTP, JSON-RPC, and connection failures and VLC authentication failures propagate to the PLAY callback. A failed command stops the playback sequence and displays an error. A successful Kodi control still updates the controller to Playing.

Run the regression tests from the repository root after installing the locked dependencies.

```sh
poetry run python -m unittest discover -s tests/repro_cases -p test_17_failed_control_reports_playing.py -v
```
