# Handle fragmented VLC authentication messages

Read the VLC Telnet prompt and authentication result across TCP chunks. The handshake has a bounded timeout, and the connection closes if it fails. Tests cover both fragmented messages, a plain TCP greeting, and a closed connection.

Run the regression tests from the repository root after installing the locked dependencies.

```sh
poetry run python -m unittest discover -s tests/repro_cases -p test_12_vlc_fragmented_auth.py -v
```
