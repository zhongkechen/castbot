# [P2] One device-finder failure discards all healthy results

## Problem and prerequisites

Configure at least two finders: one returns devices, while another times out or encounters a network connection error.

Expected: devices returned by the healthy finder remain available in the device menu. Observed: TimeoutError or ConnectionError propagates through `gather`, the entire refresh fails, and the healthy result is not saved.

The reproducer runs a healthy and a failing finder concurrently. In both scenarios it confirms that the healthy finder executed, while `_devices` remains empty. The timeout scenario uses valid `request_timeout=0`; only in the test, the real timeout context's one-second deadline is accelerated to 0.01 seconds. No negative configuration is used.

## Source locations

- [castbot/device.py:103](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/device.py#L103)
- [castbot/device.py:112](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/device.py#L112)

## Reproduction

Install the project's locked dependencies on this branch, then run from the repository root:

```bash
poetry install --no-root
poetry run python -m unittest discover -s tests/repro_cases -p test_07_finder_failure_isolation.py -v
```

The reproduction file runs independently and does not depend on helpers from other issue PRs. **PASS confirms that the current defect or static configuration conflict has been observed; it does not mean the issue is fixed.** The assertions record the observed behavior and should be updated or replaced after that behavior changes. This PR contains only the problem description and reproduction case; application code and CI are unchanged.

## Validation limits

Finder outputs and network errors are mocked. The case uses the real asyncio/async-timeout cancellation mechanism without performing SSDP or Chromecast discovery.
