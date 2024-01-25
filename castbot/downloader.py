import asyncio
import contextlib
import json
import os
import tempfile
from typing import Optional


class DownloadedVideo:
    def __init__(self,
                 video_filename: str,
                 thumbnail_filename: Optional[str] = None,
                 title: Optional[str] = None,
                 width: Optional[int] = None,
                 height: Optional[int] = None):
        self.video_filename = video_filename
        self.thumbnail_filename = thumbnail_filename
        self.title = title
        self.width = width
        self.height = height


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
                    downloaded_video = DownloadedVideo(video_filename, thumbnail_filename,
                                                       info_json.get("title"), info_json.get("width"), info_json.get("height"))
                else:  # "you-get"
                    output_filename = os.path.join(tmpdir, "video1")
                    process = await asyncio.create_subprocess_shell(f"you-get -O {output_filename} '{url}'")
                    video_filename = output_filename + ".mp4"
                    downloaded_video = DownloadedVideo(video_filename)
                    await process.communicate()

                yield downloaded_video
