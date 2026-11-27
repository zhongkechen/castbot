import asyncio
import contextlib
import json
import logging
import os
import re
import tempfile
from typing import Optional

from pyrogram import Client
from pyrogram.types import InlineKeyboardMarkup, LinkPreviewOptions, Message

from .youtube import youtube_playlist_id, youtube_video_id


_URL_PATTERN = re.compile(r"(http|https):\/\/([\w_-]+(?:(?:\.[\w_-]+)+))([\w.,@?^=%&:\/~+#-]*[\w@?^=%&\/~+#-])")


def extract_url(text: str | None) -> str | None:
    result = _URL_PATTERN.search(text or "")
    return result.group() if result else None


class DownloadedVideo:
    def __init__(self,
                 video_filename: str,
                 thumbnail_filename: Optional[str] = None,
                 title: str = "",
                 width: int = 0,
                 height: int = 0,
                 duration: int = 0):
        self.video_filename = video_filename
        self.thumbnail_filename = thumbnail_filename
        self.title = title
        self.width = width
        self.height = height
        self.duration = duration


class Downloader:
    def __init__(self, config, playing_videos):
        self._downloader = config.get("downloader", "yt-dlp")

        # yt-dlp doesn't support concurrent download
        concurrency = int(config.get("concurrency", 10)) if self._downloader != "yt-dlp" else 1
        self._semaphore = asyncio.Semaphore(concurrency)
        self._download_tasks = set()
        self._playing_videos = playing_videos

    @staticmethod
    def parse_link_message(message: Message):
        return extract_url(message.text) if message else None

    @contextlib.asynccontextmanager
    async def download(self, url):
        async with self._semaphore:
            with tempfile.TemporaryDirectory() as tmpdir:
                if self._downloader == "yt-dlp":
                    video_filename = os.path.join(tmpdir, "video1.mp4")

                    # download streams with specific video and audio codec. VP9 is not supported on iOS devices.
                    video_format = "/".join([
                        "bv*[vcodec~='avc|hevc|h265|h264']+ba[ext~='m4a|mp4']",
                        "b[ext=mp4][vcodec~='avc|hevc|h265|h264']"
                    ])
                    logging.info("Downloading video with yt-dlp")
                    process = await asyncio.create_subprocess_exec(
                        "yt-dlp", "-v", "-f", video_format, "-o", video_filename,
                        "--write-thumbnail", "--write-info-json", "--convert-thumbnails", "jpg", "--", url,
                    )
                    await process.communicate()
                    thumbnail_filename = os.path.join(tmpdir, "video1.jpg")
                    with open(os.path.join(tmpdir, "video1.info.json"), encoding="utf8") as info_file:
                        info = json.load(info_file)
                    downloaded_video = DownloadedVideo(
                        video_filename,
                        thumbnail_filename=thumbnail_filename if os.path.isfile(thumbnail_filename) else None,
                        title=info.get("title") or "",
                        width=info.get("width") or 0,
                        height=info.get("height") or 0,
                        duration=int(info.get("duration") or 0),
                    )
                else:  # "you-get"
                    output_filename = os.path.join(tmpdir, "video1")
                    logging.info("Downloading video with you-get")
                    process = await asyncio.create_subprocess_exec("you-get", "-O", output_filename, "--", url)
                    video_filename = output_filename + ".mp4"
                    downloaded_video = DownloadedVideo(video_filename)
                    await process.communicate()

                yield downloaded_video

    async def on_new_link(self, _: Client, message: Message):
        url = self.parse_link_message(message)

        if not url:
            return await message.reply("Not a supported link")

        task = asyncio.create_task(self.download_url(message, url))
        self._download_tasks.add(task)
        task.add_done_callback(self._download_tasks.discard)
        return None

    async def download_url(self, message: Message, url: str, reply_message=None):
        playlist_id = youtube_playlist_id(url)
        if playlist_id:
            return await self._playing_videos.on_new_youtube(message, None, reply_message, playlist_id=playlist_id)
        video_id = youtube_video_id(url)
        if video_id:
            return await self._playing_videos.on_new_youtube(message, video_id, reply_message)

        if not reply_message:
            reply_message = await message.reply(
                f"Downloading url {url}",
                link_preview_options=LinkPreviewOptions(is_disabled=True),
            )
        else:
            await reply_message.edit_text(f"Downloading url {url}")

        try:
            async with self.download(url) as downloaded_video:
                file_stats = os.stat(downloaded_video.video_filename)
                await reply_message.edit_text(f"Download completed. Uploading video (size={file_stats.st_size})")
                reader = open(downloaded_video.video_filename, mode="rb")
                video_message = await message.reply_video(
                    reader,
                    caption=downloaded_video.title,
                    width=downloaded_video.width,
                    height=downloaded_video.height,
                    thumb=downloaded_video.thumbnail_filename,
                    duration=downloaded_video.duration,
                )
            await reply_message.edit_text("Upload completed.")
            await reply_message.delete()
            await self._playing_videos.on_new_video(None, video_message, link_message=message)
        except Exception as e:
            logging.exception("Failed to download %s", url)

            from .button import RetryButton  # pylint: disable=C0415
            buttons = [[RetryButton(self).get_button()]]
            await reply_message.edit_text(f"Exception thrown {e} when downloading {url}",
                                          reply_markup=InlineKeyboardMarkup(buttons))
        return None
