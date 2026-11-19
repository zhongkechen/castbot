"""Downloader argument handling with a mocked process boundary."""

import json
import os
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


class DownloadArgumentsTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        task_tmpdir = os.environ.get("TMPDIR")
        if not task_tmpdir:
            self.skipTest("Set TMPDIR to a writable directory for local output fixtures.")
        original_factory = tempfile.TemporaryDirectory
        working_directory = original_factory(prefix="castbot downloads ", dir=task_tmpdir)
        self.addCleanup(working_directory.cleanup)
        factory_patch = patch.object(
            downloader_module.tempfile,
            "TemporaryDirectory",
            side_effect=lambda: original_factory(dir=working_directory.name),
        )
        factory_patch.start()
        self.addCleanup(factory_patch.stop)

    async def capture_arguments(self, backend, url):
        parsed = downloader_module.Downloader.parse_link_message(SimpleNamespace(text=url))
        self.assertEqual(parsed, url)

        async def completed_download(*argv):
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

        exec_process = AsyncMock(side_effect=completed_download)
        downloader = downloader_module.Downloader({"downloader": backend}, None)
        with (
            patch.object(downloader_module.asyncio, "create_subprocess_exec", exec_process),
            patch.object(downloader_module.asyncio, "create_subprocess_shell",
                         side_effect=AssertionError("The downloader must not launch a shell")),
        ):
            async with downloader.download(parsed) as video:
                self.assertTrue(Path(video.video_filename).is_file())

        exec_process.assert_awaited_once()
        return exec_process.await_args.args

    async def test_query_and_output_path_are_single_arguments(self):
        url = "https://media.invalid/watch?v=dummy&list=dummy"
        for backend, output_option in (("yt-dlp", "-o"), ("you-get", "-O")):
            with self.subTest(backend=backend):
                argv = await self.capture_arguments(backend, url)
                self.assertEqual(argv[0], backend)
                self.assertEqual(argv[-2:], ("--", url))
                self.assertIn("castbot downloads ", argv[argv.index(output_option) + 1])
                if backend == "yt-dlp":
                    self.assertIn("bv*[vcodec", argv[argv.index("-f") + 1])


if __name__ == "__main__":
    unittest.main(verbosity=2)
