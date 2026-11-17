# [P2] Logs expose device passwords and reversible media tokens

## Problem and prerequisites

DeviceFinder logs the complete device configuration at INFO, including the device password. The stream handler logs the reversible LocalToken and all HTTP request headers at INFO. LocalToken's hexadecimal string includes both `message_id` and the access token, which can be recovered through deserialization.

The prerequisites are that the relevant logging is enabled (the image's `-vv` enables INFO) and a log reader lacks permission to access the corresponding device or media. Expected: diagnostic logs do not expose passwords or media access capabilities to that reader. Observed: device passwords, access tokens, and sensitive request headers are recorded verbatim.

The case captures a dummy password from real WebDeviceFinder initialization logging, invokes an authorized real Http GET handler, and parses the captured log to recover the complete dummy media token. It also confirms that a dummy Authorization header is logged.

## Source locations

- [castbot/device.py:62](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/device.py#L62)
- [castbot/http.py:285](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/http.py#L285)
- [castbot/http.py:329](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/http.py#L329)
- [castbot/utils.py:25](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/utils.py#L25)
- [Dockerfile:26](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/Dockerfile#L26)

## Reproduction

Run from the repository root after installing the locked dependencies:

```bash
poetry install --no-root
poetry run python -m unittest discover -s tests/repro_cases -p test_05_sensitive_log_data.py -v
```

The reproduction file runs independently and does not depend on helpers from other issue PRs. **PASS confirms that the current defect or static configuration conflict has been observed; it does not mean the issue is fixed.** The assertions record the observed behavior and should be updated or replaced after that behavior changes. This PR contains only the problem description and reproduction case; application code and CI are unchanged.

## Validation limits

All passwords, tokens, document references, and HTTP headers are synthetic. Message RPC, stream writes, and transport are mocked; no network or real deployment logs are accessed. The case validates the direct logging mechanism, not the log-access permissions of a particular deployment. Security severity depends on that permission boundary.
