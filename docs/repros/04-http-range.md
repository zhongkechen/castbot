# [P1] HTTP Range byte counts disagree with response lengths

## Problem and prerequisites

When a player requests a byte range or seeks, the inclusive HTTP Range end is treated as an exclusive limit, while Content-Length always declares the complete file size.

## Source locations

- [castbot/http.py#L68](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/http.py#L68)
- [castbot/http.py#L141](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/http.py#L141)
- [castbot/http.py#L278](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/http.py#L278)
- [castbot/http.py#L302](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/http.py#L302)

## Reproduction

Use the eight-byte media `ABCDEFGH`, four-byte blocks, and the real handler: `bytes=2-4` returns `CD` instead of `CDE`; `bytes=4-` returns four bytes while declaring eight; `bytes=0-0` returns an empty body instead of `A`; and `bytes=0-7` loses `H`. Suffix ranges and end positions beyond EOF also return HTTP 400.

The independent unittest uses dummy messages, tokens, and in-memory data. It executes the real handler while mocking Telegram I/O and response transport. No service is started, no network is accessed, and no real credentials are required.

```bash
poetry run python -m unittest discover -s tests/repro_cases -p test_04_http_range.py -v
```

The reproduction file runs independently and does not depend on helpers from other issue PRs. **PASS confirms that the current defect or static configuration conflict has been observed; it does not mean the issue is fixed.** The assertions record the observed behavior and should be updated or replaced after that behavior changes. This PR contains only the problem description and reproduction case; application code and CI are unchanged.

## Validation limits

Executed on Python 3.14 with the locked dependencies from dfba532: 2/2 unittest methods passed. Execution is offline; no real Telegram service or TV/browser player was tested. Application code is unchanged.
