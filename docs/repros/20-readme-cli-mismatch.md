## Problem

The README pip example uses `-v 1`, but the actual `-v` option is a count flag and does not accept a numeric argument. The README also states Python 3.8+, while the project declares a minimum of Python 3.11.

This PR adds a problem record and an independently runnable offline reproduction case. Review priority: **P3**.

## Trigger

Start the application with the README pip command, or prepare an environment according to the documented minimum Python version. The command case requires a writable `TMPDIR`.

## Expected and observed

- Expected: the documented command is accepted by the CLI, and the minimum version agrees with the package's Python requirement.
- Observed: the command extracted from the README exits with code 2 when passed to the real `entry_point`, reporting `unrecognized arguments: 1` before startup. The version case finds that the documented 3.8 is below the project's 3.11 requirement.

## Source locations

- [README.md:32](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/README.md#L32)
- [README.md:35](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/README.md#L35)
- [castbot/__main__.py:65](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/__main__.py#L65)
- [pyproject.toml:12](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/pyproject.toml#L12)

## Reproduce

From the repository root, in an environment with the project's locked dependencies installed:

```bash
poetry run python -m unittest discover -s tests/repro_cases -p test_20_readme_cli_mismatch.py -v
```

The case reads the actual README command and replaces only its config path with a minimal valid TOML file under `TMPDIR`. It invokes the real `entry_point`, captures the parsing error, and uses a safe startup stub to prevent accidental bot startup. A separate case reads and compares the minimum versions in README and pyproject.toml.

**A passing test confirms that the current defect was reproduced; it does not indicate a fix.** The cases assert the observed faulty behavior. Those assertions will need to be updated or replaced when the behavior changes.

## Validation and limits

Local offline execution with Python 3.14: **2 tests passed**.

- Installation is not attempted with Python 3.8. The version discrepancy is established from the actual README and package requirement.
- No Telegram session or bot is started. The temporary configuration contains only dummy reproduction fields.
