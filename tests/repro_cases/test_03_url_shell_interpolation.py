"""A passing case confirms URL text becomes shell syntax; no shell is executed."""

import json
import os
import shlex
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import castbot.downloader as downloader_module


class CompletedProcess:
    returncode = 0

    async def communicate(self):
        return None, None


class UrlShellInterpolationReproduction(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        task_tmpdir = os.environ.get("TMPDIR")
        if not task_tmpdir:
            self.skipTest("Set TMPDIR to a writable directory for local output fixtures.")
        original_factory = tempfile.TemporaryDirectory
        working_directory = original_factory(prefix="castbot-url-shell-repro-", dir=task_tmpdir)
        self.addCleanup(working_directory.cleanup)
        factory_patch = patch.object(
            downloader_module.tempfile,
            "TemporaryDirectory",
            side_effect=lambda: original_factory(dir=working_directory.name),
        )
        factory_patch.start()
        self.addCleanup(factory_patch.stop)

    async def captured_shell_command(self, backend, url):
        parsed = downloader_module.Downloader.parse_link_message(SimpleNamespace(text=url))
        self.assertEqual(parsed, url)

        async def completed_download(command):
            # Interpret only options needed to create fixtures. Never execute this command.
            argv = shlex.split(command)
            if backend == "yt-dlp":
                output = Path(argv[argv.index("-o") + 1])
                output.write_bytes(b"dummy-media")
                output.with_suffix(".jpg").write_bytes(b"dummy-thumbnail")
                output.with_suffix(".info.json").write_text(
                    json.dumps({"title": "dummy", "width": 64, "height": 64, "duration": 3}),
                    encoding="utf-8",
                )
            else:
                output_prefix = argv[argv.index("-O") + 1]
                Path(output_prefix + ".mp4").write_bytes(b"dummy-media")
            return CompletedProcess()

        mocked_shell = AsyncMock(side_effect=completed_download)
        downloader = downloader_module.Downloader({"downloader": backend}, None)
        with patch.object(downloader_module.asyncio, "create_subprocess_shell", mocked_shell):
            async with downloader.download(parsed) as video:
                self.assertTrue(Path(video.video_filename).is_file())

        mocked_shell.assert_awaited_once()
        command = mocked_shell.await_args.args[0]
        self.assertTrue(command.endswith(" " + url))
        lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        return list(lexer)

    async def test_admin_url_suffix_is_a_separate_shell_command(self):
        url = "https://media.invalid/video.mp4&id"
        for backend in ["yt-dlp", "you-get"]:
            with self.subTest(backend=backend):
                tokens = await self.captured_shell_command(backend, url)
                separator = tokens.index("&")
                self.assertEqual(tokens[separator - 1], "https://media.invalid/video.mp4")
                self.assertEqual(tokens[-1], "id")
                self.assertEqual(separator, len(tokens) - 2)
                self.assertNotIn(url, tokens)
        print("Observed: both download backends pass '&id' as independent shell command syntax.")

    async def test_normal_ampersand_query_is_not_a_single_url_argument(self):
        url = "https://media.invalid/watch?v=dummy&list=dummy"
        for backend in ["yt-dlp", "you-get"]:
            with self.subTest(backend=backend):
                tokens = await self.captured_shell_command(backend, url)
                separator = tokens.index("&")
                self.assertEqual(tokens[separator - 1], "https://media.invalid/watch?v=dummy")
                self.assertEqual(tokens[-1], "list=dummy")
                self.assertEqual(separator, len(tokens) - 2)
                self.assertNotIn(url, tokens)
        print("Observed: both backends split a normal '&list=' query at shell operator '&'.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
