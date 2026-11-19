"""Check the system-installed entry point used by the Docker image."""
import json
import re
import unittest
from pathlib import Path

import castbot

REPOSITORY = Path(castbot.__file__).resolve().parents[1]


class DockerEntrypointTest(unittest.TestCase):
    def test_runtime_commands_use_the_system_installed_script(self):
        dockerfile = (REPOSITORY / "Dockerfile").read_text(encoding="utf-8")
        disabled = re.search(r"^ENV\s+POETRY_VIRTUALENVS_CREATE=(\S+)\s*$", dockerfile, re.MULTILINE)
        command = re.search(r"^CMD\s+(\[.*\])\s*$", dockerfile, re.MULTILINE)
        self.assertIsNotNone(disabled)
        self.assertIsNotNone(command)
        self.assertIn(disabled.group(1).lower(), {"0", "false"})
        argv = json.loads(command.group(1))
        self.assertEqual(argv, ["castbot", "-vv"])
        healthcheck = re.search(r"^HEALTHCHECK CMD\s+(\[.*\])\s*$", dockerfile, re.MULTILINE)
        self.assertIsNotNone(healthcheck)
        self.assertEqual(json.loads(healthcheck.group(1)), ["castbot", "--healthcheck"])
        self.assertIn('castbot = "castbot.__main__:entry_point"', (REPOSITORY / "pyproject.toml").read_text())
        installs = re.findall(r"^RUN\s+.*poetry install.*$", dockerfile, re.MULTILINE)
        self.assertEqual(len(installs), 2)
        self.assertFalse(re.search(r"^RUN\s+.*(?:-m venv|virtualenv\s+).*", dockerfile, re.MULTILINE))


if __name__ == "__main__":
    unittest.main(verbosity=2)
