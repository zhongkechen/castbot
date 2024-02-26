import asyncio
import logging
import os
import os.path
import re

from pyrogram import Client, filters
from pyrogram.filters import create
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from pyrogram.types import Message, CallbackQuery

from .button import Buttons
from .client import BotClient
from .video import PlayingVideos
from .device import DeviceFinderCollection
from .utils import UnknownCallbackException, LocalToken

__all__ = ["Bot"]

_URL_PATTERN = r"(http|https):\/\/([\w_-]+(?:(?:\.[\w_-]+)+))([\w.,@?^=%&:\/~+#-]*[\w@?^=%&\/~+#-])"


class Bot:
    def __init__(
        self,
        config,
        downloader,
        bot_client: BotClient,
        playing_videos: PlayingVideos,
        finders: DeviceFinderCollection,
        buttons: Buttons,
    ):
        self._bot_client = bot_client
        self._downloader = downloader
        self._buttons = buttons
        self._admins = config["admins"]
        if not isinstance(self._admins, list):
            raise ValueError("admins should be a list")
        if not all(isinstance(x, int) for x in self._admins):
            raise ValueError("admins list should contain only integers")

        self._playing_videos = playing_videos
        self._finders = finders
        self._download_tasks = set()

    async def start(self):
        admin_filter = filters.chat(self._admins) & filters.private
        self._bot_client.register(MessageHandler(self._new_document, filters.document & admin_filter))
        self._bot_client.register(MessageHandler(self._new_document, filters.video & admin_filter))
        self._bot_client.register(MessageHandler(self._new_document, filters.audio & admin_filter))
        self._bot_client.register(MessageHandler(self._new_document, filters.animation & admin_filter))
        self._bot_client.register(MessageHandler(self._new_document, filters.voice & admin_filter))
        self._bot_client.register(MessageHandler(self._new_document, filters.video_note & admin_filter))
        self._bot_client.register(MessageHandler(self._new_link, filters.text & admin_filter))

        admin_filter_inline = create(lambda _, __, m: m.from_user.id in self._admins)
        self._bot_client.register(CallbackQueryHandler(self._callback_handler, admin_filter_inline))
        await self._bot_client.start()

    async def _callback_handler(self, _: Client, message: CallbackQuery):
        button = await self._buttons.create_button_from_callback(message)
        if not button:
            raise UnknownCallbackException

        await button.on_click(message)

    async def _new_document(self, _: Client, video_message: Message, link_message=None, control_message=None):
        user_id = (link_message or video_message).from_user.id
        local_token = LocalToken(video_message.id)

        video = self._playing_videos.new_video(local_token, user_id, video_message, control_message, link_message)
        await video.send_stopped_control_message()

    async def _download_url(self, client, message, url):
        reply_message = await message.reply(
            f"Downloading url {url}",
            reply_to_message_id=message.id,
            disable_web_page_preview=True,
        )
        try:
            async with self._downloader.download(url) as downloaded_video:
                file_stats = os.stat(downloaded_video.video_filename)
                await reply_message.edit_text(f"Download completed. Uploading video (size={file_stats.st_size})")
                reader = open(downloaded_video.video_filename, mode="rb")
                video_message = await message.reply_video(
                    reader,
                    quote=True,
                    caption=downloaded_video.title or "",
                    width=downloaded_video.width or 0,
                    height=downloaded_video.height or 0,
                    thumb=downloaded_video.thumbnail_filename,
                    reply_to_message_id=message.id,
                )
            await reply_message.edit_text("Upload completed.")
            await self._new_document(
                client,
                video_message,
                link_message=message,
                control_message=reply_message,
            )
        except Exception as e:
            logging.exception("Failed to download %s", url)
            await reply_message.edit_text(f"Exception thrown {e} when downloading {url}")

    async def _new_link(self, _: Client, message: Message):
        text = message.text.strip()

        result = re.search(_URL_PATTERN, text)
        if not result:
            return await message.reply("Not a supported link")

        url = result.group()
        task = asyncio.create_task(self._download_url(_, message, url))
        self._download_tasks.add(task)
        task.add_done_callback(self._download_tasks.discard)
