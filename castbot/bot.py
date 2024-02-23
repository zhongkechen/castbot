import asyncio
import functools
import logging
import os
import os.path
import pickle
import re
import typing

from async_lru import alru_cache
from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.errors import FloodWait
from pyrogram.filters import create
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from pyrogram.handlers.handler import Handler
from pyrogram.raw.functions.auth import ExportAuthorization, ImportAuthorization
from pyrogram.raw.functions.help import GetConfig
from pyrogram.raw.functions.messages import GetMessages
from pyrogram.raw.functions.upload import GetFile
from pyrogram.raw.types import InputMessageID, InputDocumentFileLocation
from pyrogram.raw.types import Message as RawMessage
from pyrogram.raw.types.upload import File
from pyrogram.session import Session, Auth
from pyrogram.types import Message, CallbackQuery

from .video import PlayingVideos
from .http import BotInterface
from .device import DeviceFinderCollection, Device
from .utils import (
    NoDeviceException,
    ActionNotSupportedException,
    UnknownCallbackException,
    LocalToken,
)

__all__ = ["Bot"]

_URL_PATTERN = r"(http|https):\/\/([\w_-]+(?:(?:\.[\w_-]+)+))([\w.,@?^=%&:\/~+#-]*[\w@?^=%&\/~+#-])"


class UserData:
    selected_device: typing.Optional[Device] = None

    def __init__(self, selected_device):
        self.selected_device = selected_device


class BotClient(BotInterface):
    def __init__(self, config):
        self._session_name = str(config["session_name"])
        self._api_id = int(config["api_id"])
        self._api_hash = str(config["api_hash"])
        self._token = str(config["token"])
        self._file_fake_fw_wait = float(config.get("file_fake_fw_wait", 0.2))

        self._client = Client(
            self._session_name,
            self._api_id,
            self._api_hash,
            bot_token=self._token,
            sleep_threshold=0,
            workdir=os.getcwd(),
        )

    def register(self, handler: Handler):
        self._client.add_handler(handler)

    async def reply_message(self, message_id: int, chat_id: int, text: str):
        await self._client.send_message(
            chat_id,
            text=text,
            parse_mode=ParseMode.HTML,
            reply_to_message_id=message_id,
        )

    @alru_cache
    async def get_message(self, message_id: int) -> Message:
        messages = await self._client.invoke(GetMessages(id=[InputMessageID(id=message_id)]))

        if not messages.messages:
            raise ValueError("wrong message_id")

        message = messages.messages[0]

        if not isinstance(message, RawMessage):
            raise ValueError(f"expected `Message`, found: `{type(message).__name__}`")

        return message

    async def health_check(self):
        if not all(x.is_started.is_set() for x in self._client.media_sessions.values()):
            logging.log(logging.ERROR, "media session not connected")
            raise ConnectionError()

        if not self._client.session.is_started.is_set():
            logging.log(logging.ERROR, "main session not connected")
            raise ConnectionError()

    async def get_block(self, message: RawMessage, offset: int, block_size: int) -> bytes:
        session = self._client.media_sessions.get(message.media.document.dc_id)

        request = GetFile(
            offset=offset,
            limit=block_size,
            location=InputDocumentFileLocation(
                id=message.media.document.id,
                access_hash=message.media.document.access_hash,
                file_reference=b"",
                thumb_size="",
            ),
        )

        result: typing.Optional[File] = None

        while not isinstance(result, File):
            try:
                result = await session.invoke(request, sleep_threshold=0)
            except FloodWait:  # file floodwait is fake
                await asyncio.sleep(self._file_fake_fw_wait)

        return result.bytes

    async def start(self):
        await self._client.start()

        config = await self._client.invoke(GetConfig())
        dc_ids = [x.id for x in config.dc_options]
        keys_path = self._session_name + ".keys"

        if os.path.exists(keys_path):
            keys = pickle.load(open(keys_path, "rb"))
        else:
            keys = {}

        for dc_id in dc_ids:
            session = functools.partial(
                Session,
                self._client,
                dc_id,
                is_media=True,
                test_mode=False,
            )

            if dc_id != await self._client.storage.dc_id():
                if dc_id not in keys:
                    exported_auth = await self._client.invoke(ExportAuthorization(dc_id=dc_id))

                    auth = Auth(self._client, dc_id, False)
                    auth_key = await auth.create()

                    session = session(auth_key)
                    await session.start()

                    await session.invoke(ImportAuthorization(id=exported_auth.id, bytes=exported_auth.bytes))
                    keys[dc_id] = session.auth_key

                else:
                    session = session(keys[dc_id])
                    await session.start()

            else:
                session = session(await self._client.storage.auth_key())
                await session.start()

            self._client.media_sessions[dc_id] = session

        pickle.dump(keys, open(keys_path, "wb"))
        logging.info("Telegram server connected")


class Bot(BotClient):
    def __init__(self, config, downloader, playing_videos: PlayingVideos, finders: DeviceFinderCollection):
        super().__init__(config)
        self._downloader = downloader
        self._admins = config["admins"]
        if not isinstance(self._admins, list):
            raise ValueError("admins should be a list")
        if not all(isinstance(x, int) for x in self._admins):
            raise ValueError("admins list should contain only integers")

        self._playing_videos = playing_videos
        self._finders = finders
        self._user_data: typing.Dict[int, UserData] = {}

        self.prepare()

    def prepare(self):
        admin_filter = filters.chat(self._admins) & filters.private
        self.register(MessageHandler(self._new_document, filters.document & admin_filter))
        self.register(MessageHandler(self._new_document, filters.video & admin_filter))
        self.register(MessageHandler(self._new_document, filters.audio & admin_filter))
        self.register(MessageHandler(self._new_document, filters.animation & admin_filter))
        self.register(MessageHandler(self._new_document, filters.voice & admin_filter))
        self.register(MessageHandler(self._new_document, filters.video_note & admin_filter))
        self.register(MessageHandler(self._new_link, filters.text & admin_filter))

        admin_filter_inline = create(lambda _, __, m: m.from_user.id in self._admins)
        self.register(CallbackQueryHandler(self._callback_handler, admin_filter_inline))

    def _get_user_device(self, user_id):
        user_data = self._user_data.get(user_id)
        if not user_data or not user_data.selected_device:
            return None

        return user_data.selected_device

    def find_device(self, device_name, user_id):
        return self._finders.find_device_by_name(device_name) or self._get_user_device(user_id)

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
                                                                             self)

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
        self._user_data[playing_video.user_id] = UserData(device)  # Update the user's default device

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

        url = result.group(0)
        asyncio.create_task(self._download_url(_, message, url))
