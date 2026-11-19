"""Keep the README examples aligned with the supported CLI and Python version."""

import asyncio
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


class ReadmeCommandTest(unittest.TestCase):
    def test_the_documented_pip_command_runs_the_cli(self):
        readme = (REPOSITORY / "README.md").read_text(encoding="utf-8")
        match = re.search(r"^castbot -c .+$", readme, re.MULTILINE)
        self.assertIsNotNone(match, "The test must use the actual documented command.")
        argv = shlex.split(match.group(0))
        task_tmpdir = os.environ.get("TMPDIR")
        if not task_tmpdir:
            self.skipTest("Set TMPDIR to a writable directory for the minimal config fixture.")

        with tempfile.TemporaryDirectory(prefix="castbot-readme-repro-", dir=task_tmpdir) as directory:
            config = Path(directory) / "config.toml"
            config.write_text("[reproduction]\nvalue = 1\n", encoding="utf-8")
            argv[argv.index("-c") + 1] = str(config)
            safe_loop = SimpleNamespace(run_until_complete=asyncio.run)
            with (
                patch.object(main_module.sys, "argv", argv),
                patch.object(main_module, "async_main", new_callable=AsyncMock) as startup,
                patch.object(main_module.asyncio, "get_event_loop", return_value=safe_loop),
            ):
                main_module.entry_point()
            startup.assert_awaited_once_with({"reproduction": {"value": 1}})

    def test_documented_python_minimum_matches_package_requirement(self):
        readme = (REPOSITORY / "README.md").read_text(encoding="utf-8")
        metadata = tomllib.loads((REPOSITORY / "pyproject.toml").read_text(encoding="utf-8"))
        documented = re.search(r"Note: Make sure you have a version of Python (\d+\.\d+)\+", readme)
        declared = re.search(r">=\s*(\d+\.\d+)", metadata["tool"]["poetry"]["dependencies"]["python"])
        self.assertIsNotNone(documented)
        self.assertIsNotNone(declared)
        documented_version = tuple(map(int, documented.group(1).split(".")))
        declared_version = tuple(map(int, declared.group(1).split(".")))
        self.assertEqual(documented_version, declared_version)


if __name__ == "__main__":
    unittest.main(verbosity=2)
