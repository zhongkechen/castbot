# [P2] Health checks report HTTP 500 as healthy

## Problem

When the Telegram session is disconnected, the real `/healthcheck` handler returns HTTP 500. The CLI health_check function only observes whether the request raises an exception; it does not check the response status and returns exit code 0. Docker HEALTHCHECK therefore cannot distinguish a healthy bot from this disconnected state.

## Expected and observed behavior

- Expected: HTTP 500 produces a nonzero result, while HTTP 200 produces 0.
- Observed: HTTP 500 and HTTP 200 responses from the real server handler both produce 0 when supplied to the real CLI through a mocked HTTP transport boundary.

Sources: [CLI check](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/__main__.py#L49), [Server response](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/http.py#L162).

## Reproduction

Run from the repository root:

```bash
poetry install --no-root
poetry run python -m unittest discover -s tests/repro_cases -p test_14_healthcheck_http_status.py -v
```

The independent case instantiates the real Http class, simulates a Telegram session check raising ConnectionError, and obtains the real HTTP 500 Response. A fake ClientSession passes that response to the real CLI check. A separate HTTP 200 control is included.

The test asserts the current defect: **PASS confirms reproduction, not remediation**. This PR adds only the description and reproduction case; update or replace these assertions when the behavior changes.

## Validation boundaries

Telegram session state and HTTP transport are mocked. The case does not connect to Telegram or start an HTTP service or Docker container. There are two automated cases, with no dependency on other reproduction PRs.
