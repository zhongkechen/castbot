import asyncio
import logging
import os
import os.path
import re

from pyrogram import Client, filters
from pyrogram.filters import create
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from pyrogram.types import Message, CallbackQuery

from .client import BotClient
from .video import PlayingVideos
from .device import DeviceFinderCollection
from .utils import (
    NoDeviceException,
    ActionNotSupportedException,
    UnknownCallbackException,
    LocalToken,
)

__all__ = ["Bot"]

_URL_PATTERN = r"(http|https):\/\/([\w_-]+(?:(?:\.[\w_-]+)+))([\w.,@?^=%&:\/~+#-]*[\w@?^=%&\/~+#-])"


class Bot:
    def __init__(self,
                 config,
                 downloader,
                 bot_client: BotClient,
                 playing_videos: PlayingVideos,
                 finders: DeviceFinderCollection):
        self._bot_client = bot_client
        self._downloader = downloader
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
        data = message.data
        if data.count(":") == 3:
            # the old format
            _, message_id, token, payload = data.split(":")
            local_token = LocalToken(message_id, token)
        else:
            _, local_token_raw, payload = data.split(":")
            local_token = LocalToken.deserialize(local_token_raw)
        playing_video = await self._playing_videos.reconstruct_playing_video(local_token,
                                                                             message.from_user.id,
                                                                             message.message,
                                                                             self._bot_client)

        if data.startswith("s:"):
            return await self._callback_select_device(playing_video, payload, message)

        if data.startswith("c:"):
            try:
                return await self._callback_control_playback(playing_video, payload, message)
            except NoDeviceException:
                await message.answer("Device not selected")
            except ActionNotSupportedException:
                await message.answer("Action not supported by the device")
            except Exception as ex:
                logging.exception("Failed to control the device")
                await message.answer(f"Internal error: {ex.__class__.__name__}")

        raise UnknownCallbackException

    async def _callback_control_playback(self, playing_video, action, message: CallbackQuery):
        if action in ["DEVICE", "REFRESH"]:
            if action == "REFRESH":
                await self._finders.refresh_all_devices()
            return await playing_video.send_select_device_message(await self._finders.list_all_devices())

        # async with async_timeout.timeout(self._finders.device_request_timeout) as timeout_context:
        if action == "PLAY":
            await playing_video.play()
            await message.answer("Playing")
        elif action == "STOP":
            await playing_video.stop()
            await message.answer("Stopped")
        elif action == "PAUSE":
            await playing_video.pause()
            await message.answer("Paused")
        elif action == "RESUME":
            await playing_video.resume()
            await message.answer("Resumed")
        # if timeout_context.expired:
        #    await message.answer("Timeout while communicate with the device")

    async def _callback_select_device(self, playing_video, device_name, message: CallbackQuery):
        device = await self._finders.find_device_by_name(device_name)
        if not device:
            return await message.answer("Wrong device")

        await playing_video.select_device(device)

    async def _new_document(self, _: Client, video_message: Message, link_message=None, control_message=None):
        user_id = (link_message or video_message).from_user.id
        device = self._get_user_device(user_id)
        local_token = LocalToken(video_message.id)

        video = self._playing_videos.new_video(local_token,
                                               user_id,
                                               device,
                                               video_message,
                                               control_message,
                                               link_message)
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
