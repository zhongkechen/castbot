"""A passing case confirms README/CLI incompatibilities; it is not a fix."""

import contextlib
import io
import os
import re
import shlex
import tempfile
import tomllib
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import castbot.__main__ as main_module

REPOSITORY = Path(main_module.__file__).resolve().parents[1]


class ReadmeCommandReproduction(unittest.TestCase):
    def test_the_documented_pip_command_is_rejected_before_startup(self):
        readme = (REPOSITORY / "README.md").read_text(encoding="utf-8")
        match = re.search(r"^castbot -c \S+ -v 1$", readme, re.MULTILINE)
        self.assertIsNotNone(match, "The reproducer must use the actual documented command.")
        argv = shlex.split(match.group(0))
        task_tmpdir = os.environ.get("TMPDIR")
        if not task_tmpdir:
            self.skipTest("Set TMPDIR to a writable directory for the minimal config fixture.")

        with tempfile.TemporaryDirectory(prefix="castbot-readme-repro-", dir=task_tmpdir) as directory:
            config = Path(directory) / "config.toml"
            config.write_text("[reproduction]\nvalue = 1\n", encoding="utf-8")
            argv[argv.index("-c") + 1] = str(config)
            stderr = io.StringIO()
            # If argument behavior changes, these stubs prevent any real bot startup.
            safe_loop = SimpleNamespace(run_until_complete=lambda coroutine: coroutine.close())
            with patch.object(main_module.sys, "argv", argv):
                with patch.object(main_module, "async_main", new_callable=AsyncMock) as startup:
                    with patch.object(main_module.asyncio, "get_event_loop", return_value=safe_loop):
                        with contextlib.redirect_stderr(stderr):
                            with self.assertRaises(SystemExit) as raised:
                                main_module.entry_point()
                    startup.assert_not_called()

        self.assertEqual(raised.exception.code, 2)
        self.assertIn("unrecognized arguments: 1", stderr.getvalue())
        print("Observed: README's -v 1 command exits 2 with unrecognized arguments: 1, before startup.")

    def test_documented_python_minimum_is_below_package_requirement(self):
        readme = (REPOSITORY / "README.md").read_text(encoding="utf-8")
        metadata = tomllib.loads((REPOSITORY / "pyproject.toml").read_text(encoding="utf-8"))
        documented = re.search(r"Note: Make sure you have a version of Python (\d+\.\d+)\+", readme)
        declared = re.search(r">=\s*(\d+\.\d+)", metadata["tool"]["poetry"]["dependencies"]["python"])
        self.assertIsNotNone(documented)
        self.assertIsNotNone(declared)
        documented_version = tuple(map(int, documented.group(1).split(".")))
        declared_version = tuple(map(int, declared.group(1).split(".")))
        self.assertLess(documented_version, declared_version)
        print(f"Observed: README permits Python {documented.group(1)}+, but package requires {declared.group(1)}+.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
