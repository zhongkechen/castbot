import asyncio
import functools
import html
import logging
import os
import os.path
import pickle
import re
import traceback
import typing

import pyrogram
import pyrogram.session
from async_lru import alru_cache
from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.errors import FloodWait
from pyrogram.errors import MessageNotModified
from pyrogram.filters import create
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from pyrogram.handlers.handler import Handler
from pyrogram.raw.functions.auth import ExportAuthorization, ImportAuthorization
from pyrogram.raw.functions.help import GetConfig
from pyrogram.raw.functions.messages import GetMessages
from pyrogram.raw.functions.upload import GetFile
from pyrogram.raw.types import InputMessageID, InputDocumentFileLocation
from pyrogram.raw.types.upload import File
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from . import Http, BotInterface, DeviceFinderCollection
from .device import Device
from .utils import secret_token, serialize_token, NoDeviceException, ActionNotSupportedException, \
    UnknownCallbackException

__all__ = [
    "Bot"
]

_URL_PATTERN = r'(http|https):\/\/([\w_-]+(?:(?:\.[\w_-]+)+))([\w.,@?^=%&:\/~+#-]*[\w@?^=%&\/~+#-])'


class UserData:
    selected_device: typing.Optional[Device] = None

    def __init__(self, selected_device):
        self.selected_device = selected_device


class PlayingVideo:
    def __init__(self,
                 token: int,
                 user_id: int,
                 video_message: typing.Optional[Message] = None,
                 playing_device: typing.Optional[Device] = None,
                 control_message: typing.Optional[Message] = None,
                 link_message: typing.Optional[Message] = None):
        self.token = token
        self.user_id = user_id
        self.video_message = video_message
        self.playing_device: typing.Optional[Device] = playing_device
        self.control_message = control_message
        self.link_message = link_message

    def _gen_device_str(self):
        return (f"on device <code>"
                f"{html.escape(self.playing_device.get_device_name()) if self.playing_device else 'NONE'}</code>")

    @classmethod
    def parse_device_str(cls, text):
        groups = re.search("on device ([^,]*)", text)
        if not groups:
            return None
        return groups.group(1)

    def _gen_message_str(self):
        return f"for file <code>{self.video_message.id}</code>"

    def _gen_command_button(self, command):
        return InlineKeyboardButton(command, f"c:{self.video_message.id}:{self.token}:{command}")

    def _gen_device_button(self, device):
        return InlineKeyboardButton(repr(device), f"s:{self.video_message.id}:{self.token}:{repr(device)}")

    async def send_stopped_control_message(self, remaining=None):
        buttons = [[self._gen_command_button("DEVICE")], [self._gen_command_button("PLAY")]]
        if not remaining:
            text = f"Controller {self._gen_message_str()} {self._gen_device_str()}"
        else:
            text = f"Streaming closed {self._gen_message_str()} {self._gen_device_str()}, {remaining:0.2f}% remains"
        await self.create_or_update_control_message(text, buttons)

    async def send_playing_control_message(self):
        buttons = [[self._gen_command_button("STOP")], [self._gen_command_button("PAUSE")]]
        text = f"Playing {self._gen_message_str()} {self._gen_device_str()}"
        await self.create_or_update_control_message(text, buttons)

    async def send_paused_control_message(self):
        buttons = [[self._gen_command_button("STOP")], [self._gen_command_button("RESUME")]]
        text = f"Paused {self._gen_message_str()} {self._gen_device_str()}"
        await self.create_or_update_control_message(text, buttons)

    async def create_or_update_control_message(self, text, buttons):
        if self.control_message:
            try:
                await self.control_message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
            except MessageNotModified:
                pass
        else:
            self.control_message = await self.video_message.reply(text, reply_markup=InlineKeyboardMarkup(buttons))

    async def play(self, http: Http):
        if not self.playing_device:
            raise NoDeviceException

        uri = http.build_streaming_uri(self.video_message.id, self.token)
        local_token = serialize_token(self.video_message.id, self.token)

        try:
            filename = pyrogram_filename(self.video_message)
        except TypeError:
            filename = "None"

        # noinspection PyBroadException
        await self.playing_device.stop()
        await self.playing_device.play(uri, str(filename), local_token)
        await self.send_playing_control_message()

    async def stop(self):
        if self.playing_device:
            try:
                await self.playing_device.stop()
            except Exception:
                # make sure stop always succeeds even if the device is gone
                traceback.print_exc()
        await self.send_stopped_control_message()
        if not self.playing_device:
            raise NoDeviceException

    async def pause(self):
        if not self.playing_device:
            raise NoDeviceException
        if hasattr(self.playing_device, "pause"):
            await self.playing_device.pause()
            return await self.send_paused_control_message()
        raise ActionNotSupportedException

    async def resume(self):
        if not self.playing_device:
            raise NoDeviceException
        if hasattr(self.playing_device, "resume"):
            await self.playing_device.resume()
            return await self.send_playing_control_message()
        raise ActionNotSupportedException

    async def select_device(self, devices):
        buttons = [[self._gen_device_button(d)] for d in devices] + [[self._gen_command_button("REFRESH")]]
        await self.create_or_update_control_message("Select a device", buttons)


def pyrogram_filename(message: Message) -> str:
    named_media_types = ("document", "video", "audio", "video_note", "animation")
    try:
        return next(
            getattr(message, t, None).file_name for t in named_media_types if getattr(message, t, None) is not None
        )
    except StopIteration as error:
        raise TypeError() from error


class Bot(BotInterface):
    def __init__(self, config, downloader, http: Http, finders: DeviceFinderCollection):
        self._session_name = str(config["session_name"])
        self._api_id = int(config["api_id"])
        self._api_hash = str(config["api_hash"])
        self._token = str(config["token"])
        self._file_fake_fw_wait = float(config.get("file_fake_fw_wait", 0.2))
        self._client = pyrogram.Client(self._session_name,
                                       self._api_id,
                                       self._api_hash,
                                       bot_token=self._token,
                                       sleep_threshold=0,
                                       workdir=os.getcwd())

        self._downloader = downloader
        self._admins = config["admins"]
        if not isinstance(self._admins, list):
            raise ValueError("admins should be a list")
        if not all(isinstance(x, int) for x in self._admins):
            raise ValueError("admins list should contain only integers")

        self._http = http
        self._finders = finders
        self._user_data: typing.Dict[int, UserData] = {}
        self._playing_videos: typing.Dict[int, PlayingVideo] = {}

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

    async def _reconstruct_playing_video(self, message_id, token, callback: CallbackQuery):
        # re-construct PlayVideo when the bot is restarted
        user_id = callback.from_user.id
        control_message = callback.message
        video_message: Message = await self.get_message(message_id)
        if control_message.reply_to_message_id and control_message.reply_to_message_id != message_id:
            link_message = await self.get_message(control_message.reply_to_message_id)
        else:
            link_message = None

        device = (await self._finders.find_device_by_name(PlayingVideo.parse_device_str(control_message.text))
                  or self._get_user_device(user_id))
        return PlayingVideo(token,
                            user_id,
                            video_message=video_message,
                            playing_device=device,
                            control_message=control_message,
                            link_message=link_message)

    async def _callback_handler(self, _: Client, message: CallbackQuery):
        data = message.data
        _, message_id, token, payload = data.split(":")
        message_id = int(message_id)
        token = int(token)
        local_token = serialize_token(message_id, token)
        if local_token not in self._playing_videos:
            self._playing_videos[local_token] = await self._reconstruct_playing_video(message_id, token, message)

        playing_video = self._playing_videos[local_token]

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
                traceback.print_exc()

                await message.answer(f"Unknown exception: {ex.__class__.__name__}")

        raise UnknownCallbackException

    async def _callback_control_playback(self, playing_video, action, message: CallbackQuery):
        if action in ["DEVICE", "REFRESH"]:
            if action == "REFRESH":
                await self._finders.refresh_all_devices()
            return await playing_video.select_device(await self._finders.list_all_devices())

        # async with async_timeout.timeout(self._finders.device_request_timeout) as timeout_context:
        if action == "PLAY":
            self._http.add_remote_token(playing_video.video_message.id, playing_video.token)
            await playing_video.play(self._http)
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

        playing_video.playing_device = device
        await playing_video.send_stopped_control_message()
        self._user_data[playing_video.user_id] = UserData(device)  # Update the user's default device

    async def _new_document(self, _: Client, video_message: Message, link_message=None, control_message=None):
        user_id = (link_message or video_message).from_user.id
        device = self._get_user_device(user_id)
        token = secret_token()
        local_token = serialize_token(video_message.id, token)

        self._playing_videos[local_token] = PlayingVideo(token, user_id,
                                                         video_message=video_message,
                                                         playing_device=device,
                                                         control_message=control_message,
                                                         link_message=link_message)
        await self._playing_videos[local_token].send_stopped_control_message()

    async def _download_url(self, client, message, url):
        reply_message = await message.reply(f"Downloading url {url}",
                                            reply_to_message_id=message.id,
                                            disable_web_page_preview=True)
        try:
            async with self._downloader.download(url) as output_filename:
                file_stats = os.stat(output_filename)
                await reply_message.edit_text(f"Download completed. Uploading video (size={file_stats.st_size})")
                reader = open(output_filename, mode='rb')
                video_message = await message.reply_video(reader, reply_to_message_id=message.id)
            await reply_message.edit_text("Upload completed.")
            await self._new_document(client, video_message, link_message=message, control_message=reply_message)
        except Exception as e:
            await reply_message.edit_text(f"Exception thrown {e} when downloading {url}: {traceback.format_exc()}")

    async def _new_link(self, _: Client, message: Message):
        text = message.text.strip()

        result = re.search(_URL_PATTERN, text)
        if not result:
            return await message.reply("Not a supported link")

        url = result.group(0)
        asyncio.create_task(self._download_url(_, message, url))

    async def handle_closed(self, remains: float, local_token: int):
        if local_token in self._playing_videos:
            playing_video = self._playing_videos[local_token]
            device = playing_video.playing_device
            await playing_video.send_stopped_control_message(remaining=remains)
            del self._playing_videos[local_token]
            await device.on_close(local_token)

    def register(self, handler: Handler):
        self._client.add_handler(handler)

    async def reply_message(self, message_id: int, chat_id: int, text: str):
        await self._client.send_message(
            chat_id,
            text=text,
            parse_mode=ParseMode.HTML,
            reply_to_message_id=message_id
        )

    @alru_cache
    async def get_message(self, message_id: int) -> Message:
        messages = await self._client.invoke(GetMessages(id=[InputMessageID(id=message_id)]))

        if not messages.messages:
            raise ValueError("wrong message_id")

        message = messages.messages[0]

        if not isinstance(message, pyrogram.raw.types.Message):
            raise ValueError(f"expected `Message`, found: `{type(message).__name__}`")

        return message

    async def health_check(self):
        if not all(x.is_started.is_set() for x in self._client.media_sessions.values()):
            logging.log(logging.ERROR, "media session not connected")
            raise ConnectionError()

        if not self._client.session.is_started.is_set():
            logging.log(logging.ERROR, "main session not connected")
            raise ConnectionError()

    async def get_block(self, message: pyrogram.raw.types.Message, offset: int, block_size: int) -> bytes:
        session = self._client.media_sessions.get(message.media.document.dc_id)

        request = GetFile(
            offset=offset,
            limit=block_size,
            location=InputDocumentFileLocation(
                id=message.media.document.id,
                access_hash=message.media.document.access_hash,
                file_reference=b"",
                thumb_size=""
            )
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
            session = functools.partial(pyrogram.session.Session, self._client, dc_id, is_media=True, test_mode=False)

            if dc_id != await self._client.storage.dc_id():
                if dc_id not in keys:
                    exported_auth = await self._client.invoke(ExportAuthorization(dc_id=dc_id))

                    auth = pyrogram.session.Auth(self._client, dc_id, False)
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
