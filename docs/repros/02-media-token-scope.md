# [P1] Media tokens allow unauthorized access to other Telegram documents

## Problem and prerequisites

A holder of an active media URL can change `message_id` and extend `token` beyond 64 bits while preserving `(message_id << 64) ^ token`. After dictionary authorization succeeds, the HTTP handler fetches the document using the changed message ID. The target document must be accessible to the bot; this does not bypass Telegram's own access controls.

## Source locations

- [castbot/utils.py#L15](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/utils.py#L15)
- [castbot/utils.py#L23](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/utils.py#L23)
- [castbot/http.py#L233](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/http.py#L233)
- [castbot/http.py#L256](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/http.py#L256)

## Reproduction

Authorize only dummy message 1/token 2, construct a token for message 2, and invoke the real HTTP handler. Expected: rejection with HTTP 403. Observed: the fake Telegram client receives `get_message(2)` and the handler returns HTTP 200 with the complete media. Ordinary message 2/token 2 is rejected as an authorization control.

The independent unittest uses dummy messages, tokens, and in-memory data. It executes the real handler while mocking Telegram I/O and response transport. No service is started, no network is accessed, and no real credentials are required.

```bash
poetry run python -m unittest discover -s tests/repro_cases -p test_02_media_token_scope.py -v
```

The reproduction file runs independently and does not depend on helpers from other issue PRs. **PASS confirms that the current defect or static configuration conflict has been observed; it does not mean the issue is fixed.** The assertions record the observed behavior and should be updated or replaced after that behavior changes. This PR contains only the problem description and reproduction case; application code and CI are unchanged.

## Validation limits

Executed on Python 3.14 with the locked dependencies from dfba532: 2/2 unittest methods passed. Execution is offline; no real Telegram service or TV/browser player was tested. Application code is unchanged.
