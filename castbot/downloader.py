import asyncio
import contextlib
import json
import os
import tempfile


class Downloader:
    def __init__(self, config):
        self._downloader = config.get("downloader", "yt-dlp")
        self._semaphore = asyncio.Semaphore(int(config.get("concurrency", 10)))

    @contextlib.asynccontextmanager
    async def download(self, url):
        async with self._semaphore:
            with tempfile.TemporaryDirectory() as tmpdir:
                if self._downloader == "yt-dlp":
                    video_filename = os.path.join(tmpdir, "video1.mp4")
                    process = await asyncio.create_subprocess_shell(
                        f"yt-dlp -v -f mp4 -o {video_filename} "
                        f"--write-thumbnail --write-info-json --convert-thumbnails jpg '{url}'"
                    )
                    await process.communicate()
                    thumbnail_filename = os.path.join(tmpdir, "video1.jpg")
                    info_json = json.load(open(os.path.join(tmpdir, "video1.info.json"), encoding="utf8"))
                    title = info_json["title"]
                    width = info_json["width"]
                    height = info_json["height"]
                else:  # "you-get"
                    output_filename = os.path.join(tmpdir, "video1")
                    process = await asyncio.create_subprocess_shell(f"you-get -O {output_filename} '{url}'")
                    video_filename = output_filename + ".mp4"
                    thumbnail_filename = None
                    title = None
                    width = None
                    height = None
                    await process.communicate()

                yield video_filename, thumbnail_filename, title, width, height
