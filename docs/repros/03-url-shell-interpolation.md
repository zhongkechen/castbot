# [P1] Download URLs are interpolated into shell commands

## Problem and prerequisites

The URL regex accepts `&`, and the downloader inserts the extracted URL verbatim into a command string passed to `create_subprocess_shell`. Both `yt-dlp` and `you-get` cross this boundary: the shell treats `&` as a control operator rather than part of a URL query parameter.

This PR adds a problem description and an independently runnable offline reproduction case, with review priority **P1**. The case does not execute a shell or attack command.

## Preconditions

The Telegram text entry point accepts only configured bot admins. An admin must submit a link containing `&`, or be induced to submit one. Permission to control media does not itself grant permission to execute host OS commands.

The regex at the application entry point restricts available payload characters. This case covers an additional argumentless command and splitting of a legitimate query string; it does not claim that arbitrary shell arguments can be submitted directly. TMPDIR must point to a writable directory for local output placeholder files.

## Expected and observed behavior

- Expected: the entire extracted URL is one downloader argument, preserving `&` within the URL.
- Observed: lexical analysis of the captured command for `https://media.invalid/video.mp4&id` produces the URL, a separate `&` operator, and `id`. The legitimate URL `https://media.invalid/watch?v=dummy&list=dummy` also splits into two shell segments.
- Both downloader backends produce the same result. If executed, the first form can invoke an additional argumentless command; the second loses the remainder of the URL and may run the download in the background.

## Source locations

- [downloader.py:14](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/downloader.py#L14)
- [downloader.py:66](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/downloader.py#L66)
- [downloader.py:82](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/downloader.py#L82)
- [bot.py:28](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/bot.py#L28)
- [bot.py:35](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/bot.py#L35)

## Reproduction

Run from the repository root after installing the project's locked dependencies:

The case first invokes the real `Downloader.parse_link_message`, then the real `Downloader.download`. It replaces only the subprocess boundary and creates actual placeholder video, metadata, and thumbnail files to complete the download context. It then uses `shlex.shlex` with shell-operator recognition on the complete captured command, confirming that `&` is a separate operator and the URL is no longer one argument. Two tests cover an extra-command suffix and an ordinary query string; each covers both backends.

```bash
poetry run python -m unittest discover -s tests/repro_cases -p test_03_url_shell_interpolation.py -v
```

The reproduction file runs independently and does not depend on helpers from other issue PRs. **PASS confirms that the current defect or static configuration conflict has been observed; it does not mean the issue is fixed.** The assertions record the observed behavior and should be updated or replaced after that behavior changes. This PR contains only the problem description and reproduction case; application code and CI are unchanged.

## Validation limits

- No shell, yt-dlp, you-get, or `id` is executed. There is no OS payload execution or real download.
- No Telegram service, playback device, or external URL is contacted. All URLs and output data are synthetic.
- The automated case validates source-to-shell command construction and lexical boundaries. It does not measure a background-download race or actual system-command impact.
