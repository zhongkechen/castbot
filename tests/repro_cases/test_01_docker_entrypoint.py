"""Passing test confirms a static Docker configuration conflict, not a container run."""
import json
import re
import unittest
from pathlib import Path

import castbot

REPOSITORY = Path(castbot.__file__).resolve().parents[1]


class DockerEntrypointRepro(unittest.TestCase):
    def test_disabled_virtualenv_creation_and_virtualenv_entrypoint_coexist(self):
        dockerfile = (REPOSITORY / "Dockerfile").read_text(encoding="utf-8")
        disabled = re.search(r"^ENV\s+POETRY_VIRTUALENVS_CREATE=(\S+)\s*$", dockerfile, re.MULTILINE)
        command = re.search(r"^CMD\s+(\[.*\])\s*$", dockerfile, re.MULTILINE)
        self.assertIsNotNone(disabled)
        self.assertIsNotNone(command)
        self.assertIn(disabled.group(1).lower(), {"0", "false"})
        argv = json.loads(command.group(1))
        self.assertEqual(argv[0], "/app/.venv/bin/castbot")
        installs = re.findall(r"^RUN\s+.*poetry install.*$", dockerfile, re.MULTILINE)
        self.assertEqual(len(installs), 2)
        self.assertFalse(re.search(r"^RUN\s+.*(?:-m venv|virtualenv\s+).*", dockerfile, re.MULTILINE))
        print("Observed static conflict: Poetry virtualenv creation is disabled, CMD requires /app/.venv/bin/castbot.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
