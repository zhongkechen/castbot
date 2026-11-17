"""A passing case confirms the current optional-metadata defects; it is not a fix."""

import json
import os
import shlex
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import castbot.downloader as downloader_module


class CompletedProcess:
    returncode = 0

    async def communicate(self):
        return None, None


class OptionalMetadataReproduction(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        task_tmpdir = os.environ.get("TMPDIR")
        if not task_tmpdir:
            self.skipTest("Set TMPDIR to a writable directory for temporary reproduction artifacts.")
        original_factory = tempfile.TemporaryDirectory
        working_directory = original_factory(prefix="castbot-metadata-repro-", dir=task_tmpdir)
        self.addCleanup(working_directory.cleanup)
        factory_patch = patch.object(
            downloader_module.tempfile,
            "TemporaryDirectory",
            side_effect=lambda: original_factory(dir=working_directory.name),
        )
        factory_patch.start()
        self.addCleanup(factory_patch.stop)

    @staticmethod
    def completed_download(metadata):
        async def create_process(command):
            argv = shlex.split(command)
            output = Path(argv[argv.index("-o") + 1])
            output.write_bytes(b"dummy-downloaded-media")
            output.with_suffix(".info.json").write_text(json.dumps(metadata), encoding="utf-8")
            return CompletedProcess()

        return create_process

    async def test_successful_download_with_missing_duration_raises(self):
        metadata = {"title": "dummy title", "width": 64, "height": 64, "duration": None}
        downloader = downloader_module.Downloader({}, None)
        with patch.object(
            downloader_module.asyncio,
            "create_subprocess_shell",
            self.completed_download(metadata),
        ):
            with self.assertRaisesRegex(TypeError, "NoneType"):
                async with downloader.download("https://media.invalid/video.mp4"):
                    self.fail("Missing duration should currently fail before the context yields.")
        print("Observed: subprocess success plus video/info output still raises int(None) for absent duration.")

    async def test_successful_download_without_thumbnail_returns_missing_path(self):
        metadata = {"title": "dummy title", "width": 64, "height": 64, "duration": 3}
        downloader = downloader_module.Downloader({}, None)
        with patch.object(
            downloader_module.asyncio,
            "create_subprocess_shell",
            self.completed_download(metadata),
        ):
            async with downloader.download("https://media.invalid/video.mp4") as video:
                self.assertTrue(Path(video.video_filename).is_file())
                self.assertIsNotNone(video.thumbnail_filename)
                self.assertFalse(Path(video.thumbnail_filename).exists())
                print("Observed: successful media output is paired with a nonexistent thumbnail upload path.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
