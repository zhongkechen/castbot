import asyncio
import contextlib
import os
import tempfile


class Downloader:
    def __init__(self, config):
        self._downloader = config
        assert self._downloader in ["yt-dlp", "you-get"]

    @contextlib.asynccontextmanager
    async def download(self, url):
        with tempfile.TemporaryDirectory() as tmpdir:
            if self._downloader == "yt-dlp":
                output_filename = os.path.join(tmpdir, "video1.mp4")
                process = await asyncio.create_subprocess_shell(
                    f"yt-dlp -v -f mp4 -o {output_filename} '{url}'")
            else:  # "you-get"
                output_filename = os.path.join(tmpdir, "video1")
                process = await asyncio.create_subprocess_shell(f"you-get -O {output_filename} '{url}'")
                output_filename = output_filename + ".mp4"

            await process.communicate()

            yield output_filename
