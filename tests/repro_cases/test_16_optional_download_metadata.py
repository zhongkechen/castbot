"""Check that optional yt-dlp outputs do not prevent processing."""

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


class OptionalMetadataTest(unittest.IsolatedAsyncioTestCase):
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
    def completed_download(metadata, *, thumbnail=False):
        async def create_process(*arguments):
            argv = shlex.split(arguments[0]) if len(arguments) == 1 else arguments
            output = Path(argv[argv.index("-o") + 1])
            output.write_bytes(b"dummy-downloaded-media")
            output.with_suffix(".info.json").write_text(json.dumps(metadata), encoding="utf-8")
            if thumbnail:
                output.with_suffix(".jpg").write_bytes(b"dummy-thumbnail")
            return CompletedProcess()

        return create_process

    async def check_download(self, metadata, *, thumbnail=False, duration=0):
        downloader = downloader_module.Downloader({}, None)
        run_process = self.completed_download(metadata, thumbnail=thumbnail)
        with (
            patch.object(downloader_module.asyncio, "create_subprocess_shell", run_process),
            patch.object(downloader_module.asyncio, "create_subprocess_exec", run_process),
        ):
            async with downloader.download("https://media.invalid/video.mp4") as video:
                self.assertTrue(Path(video.video_filename).is_file())
                self.assertEqual(video.duration, duration)
                self.assertEqual(video.title, metadata.get("title") or "")
                self.assertEqual(video.width, metadata.get("width") or 0)
                self.assertEqual(video.height, metadata.get("height") or 0)
                if thumbnail:
                    self.assertTrue(Path(video.thumbnail_filename).is_file())
                else:
                    self.assertIsNone(video.thumbnail_filename)

    async def test_missing_duration_and_thumbnail_use_upload_defaults(self):
        for metadata in ({}, {"duration": None, "title": None, "width": None, "height": None}):
            with self.subTest(metadata=metadata):
                await self.check_download(metadata)

    async def test_existing_thumbnail_and_valid_metadata_are_kept(self):
        await self.check_download(
            {"title": "test", "width": 64, "height": 48, "duration": 3.5}, thumbnail=True, duration=3,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
