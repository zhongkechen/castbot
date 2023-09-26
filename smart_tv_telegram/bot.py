import asyncio
import html
import os
import os.path
import re
import traceback
import typing
import tempfile

import async_timeout
from pyrogram import Client, filters
from pyrogram.filters import create
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from pyrogram.types import ReplyKeyboardRemove, Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from . import Config, Mtproto, Http, OnStreamClosed, DeviceFinderCollection
from .devices import Device, DevicePlayerFunction
from .tools import build_uri, pyrogram_filename, secret_token

__all__ = [
    "Bot"
]

_REMOVE_KEYBOARD = ReplyKeyboardRemove()
_CANCEL_BUTTON = "^Cancel"
_URL_PATTERN = r'(http|https):\/\/([\w_-]+(?:(?:\.[\w_-]+)+))([\w.,@?^=%&:\/~+#-]*[\w@?^=%&\/~+#-])'


class OnStreamClosedHandler(OnStreamClosed):
    _mtproto: Mtproto
    _functions: typing.Dict[int, typing.Any]
    _devices: typing.Dict[int, Device]

    def __init__(self,
                 mtproto: Mtproto,
                 functions: typing.Dict[int, typing.Any],
                 devices: typing.Dict[int, Device]):
        self._mtproto = mtproto
        self._functions = functions
        self._devices = devices

    async def handle(self, remains: float, chat_id: int, message_id: int, local_token: int):
        if local_token in self._functions:
            del self._functions[local_token]

        on_close: typing.Optional[typing.Callable[[int], typing.Coroutine]] = None

        if local_token in self._devices:
            on_close = self._devices[local_token].on_close
            del self._devices[local_token]

        await self._mtproto.reply_message(message_id, chat_id, f"download closed, {remains:0.2f}% remains")

        if on_close is not None:
            await on_close(local_token)


class UserData:
    selected_device: typing.Optional[Device] = None

    def __init__(self, selected_device):
        self.selected_device = selected_device


class PlayingVideo:
    def __init__(self, user_id: int, video_message: Message, control_message: Message, playing_device: Device):
        self.user_id = user_id
        self.video_message = video_message
        self.control_message = control_message
        self.playing_device: typing.Optional[Device] = playing_device


class Bot:
    _config: Config
    _mtproto: Mtproto
    _http: Http
    _finders: DeviceFinderCollection
    _functions: typing.Dict[int, typing.Dict[int, typing.Union[DevicePlayerFunction, typing.Callable]]]
    _devices: typing.Dict[int, Device]
    _user_data: typing.Dict[int, UserData]
    _playing_videos: typing.Dict[int, PlayingVideo]

    def __init__(self, mtproto: Mtproto, config: Config, http: Http, finders: DeviceFinderCollection):
        self._config = config
        self._mtproto = mtproto
        self._http = http
        self._finders = finders
        self._functions = {}
        self._devices = {}
        self._all_devices = []
        self._user_data = {}
        self._playing_videos = {}

        self._http.set_on_stream_closed_handler(self.get_on_stream_closed())
        self.prepare()

    def get_on_stream_closed(self) -> OnStreamClosed:
        return OnStreamClosedHandler(self._mtproto, self._functions, self._devices)

    def prepare(self):
        admin_filter = filters.chat(self._config.admins) & filters.private
        self._mtproto.register(MessageHandler(self._new_document, filters.document & admin_filter))
        self._mtproto.register(MessageHandler(self._new_document, filters.video & admin_filter))
        self._mtproto.register(MessageHandler(self._new_document, filters.audio & admin_filter))
        self._mtproto.register(MessageHandler(self._new_document, filters.animation & admin_filter))
        self._mtproto.register(MessageHandler(self._new_document, filters.voice & admin_filter))
        self._mtproto.register(MessageHandler(self._new_document, filters.video_note & admin_filter))
        self._mtproto.register(MessageHandler(self._new_link, filters.text & admin_filter))

        admin_filter_inline = create(lambda _, __, m: m.from_user.id in self._config.admins)
        self._mtproto.register(CallbackQueryHandler(self._callback_handler, admin_filter_inline))

    def _get_user_device(self, user_id):
        user_data = self._user_data.get(user_id)
        if not user_data or not user_data.selected_device:
            return

        return user_data.selected_device

    async def _refresh_all_devices(self):
        self._all_devices = []

        for finder in self._finders.get_finders(self._config):
            with async_timeout.timeout(self._config.device_request_timeout + 1):
                self._all_devices.extend(await finder.find(self._config))

    async def _callback_handler(self, _: Client, message: CallbackQuery):
        data = message.data
        _, control_id, payload = data.split(":")
        control_id = int(control_id)

        if data.startswith("s:"):
            return await self._callback_select_device(control_id, payload, message)
        elif data.startswith("c:"):
            return await self._callback_control_playback(control_id, payload, message)

    async def _callback_control_playback(self, control_id, action, message: CallbackQuery):
        playing_video = self._playing_videos[control_id]
        msg_id = playing_video.video_message.id

        if action == "DEVICE":
            await self._refresh_all_devices()
            buttons = [[InlineKeyboardButton(repr(device), f"s:{control_id}:{repr(device)}")] for device in
                       self._all_devices]
            await playing_video.control_message.edit_text("Select a device",
                                                          reply_markup=InlineKeyboardMarkup(buttons))
            return

        async with async_timeout.timeout(self._config.device_request_timeout) as timeout_context:
            if action == "START":
                if not playing_video.playing_device:
                    return await message.answer("Device not selected")
                token = secret_token()
                local_token = self._http.add_remote_token(msg_id, token)
                device = self._devices[local_token] = playing_video.playing_device
                uri = build_uri(self._config, msg_id, token)

                try:
                    filename = pyrogram_filename(playing_video.video_message)
                except TypeError:
                    filename = "None"

                # noinspection PyBroadException
                try:
                    await device.stop()
                    await device.play(uri, str(filename), local_token)
                except Exception as ex:
                    traceback.print_exc()

                    await message.answer(
                        "Error while communicate with the device:\n\n"
                        f"<code>{html.escape(str(ex))}</code>"
                    )
                buttons = [[InlineKeyboardButton("STOP", f"c:{control_id}:STOP")],
                           [InlineKeyboardButton("PAUSE", f"c:{control_id}:PAUSE")]]
                await playing_video.control_message.edit_text(
                    f"Playing <code>{msg_id}</code> on device <code>{html.escape(device.get_device_name())}</code>",
                    reply_markup=InlineKeyboardMarkup(buttons)
                )
            elif action == "STOP":
                await playing_video.playing_device.stop()
                playing_video.playing_device = None
                buttons = [[InlineKeyboardButton("DEVICE", f"c:{control_id}:DEVICE")],
                           [InlineKeyboardButton("START", f"c:{control_id}:START")]]
                await playing_video.control_message.edit_text(
                    f"Controller for file <code>{msg_id}</code>",
                    reply_markup=InlineKeyboardMarkup(buttons)
                )
            elif action == "PAUSE":
                for function in playing_video.playing_device.get_player_functions():
                    if await function.is_enabled(self._config) and (await function.get_name()).upper() == "PAUSE":
                        await function.handle()
                        buttons = [[InlineKeyboardButton("STOP", f"c:{control_id}:STOP")],
                                   [InlineKeyboardButton("PLAY", f"c:{control_id}:PLAY")]]
                        await playing_video.control_message.edit_text(
                            f"Paused <code>{msg_id}</code> on device <code>{html.escape(playing_video.playing_device.get_device_name())}</code>",
                            reply_markup=InlineKeyboardMarkup(buttons)
                        )
                else:
                    await message.answer("Action not supported by the device")
            elif action == "PLAY":
                for function in playing_video.playing_device.get_player_functions():
                    if await function.is_enabled(self._config) and (await function.get_name()).upper() == "PLAY":
                        await function.handle()
                        buttons = [[InlineKeyboardButton("STOP", f"c:{control_id}:STOP")],
                                   [InlineKeyboardButton("PAUSE", f"c:{control_id}:PAUSE")]]
                        await playing_video.control_message.edit_text(
                            f"Playing <code>{msg_id}</code> on device <code>{html.escape(playing_video.playing_device.get_device_name())}</code>",
                            reply_markup=InlineKeyboardMarkup(buttons)
                        )
                else:
                    await message.answer("Action not supported by the device")
        if timeout_context.expired:
            await message.answer("Timeout while communicate with the device")

    async def _callback_select_device(self, control_id, device_name, message: CallbackQuery):
        playing_video = self._playing_videos[control_id]
        try:
            device = next(
                device
                for device in self._all_devices
                if repr(device) == device_name
            )
        except StopIteration:
            await message.answer("Wrong device")
            return

        playing_video.playing_device = device
        self._user_data[message.from_user.id] = UserData(device)
        buttons = [[InlineKeyboardButton("DEVICE", f"c:{control_id}:DEVICE")],
                   [InlineKeyboardButton("START", f"c:{control_id}:START")]]
        await playing_video.control_message.edit_text(
            f"Controller for file <code>{message.id}</code>",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    async def _new_document(self, _: Client, message: Message, user_message=None):
        user_id = (user_message or message).from_user.id
        control_id = secret_token()
        buttons = [[InlineKeyboardButton("DEVICE", f"c:{control_id}:DEVICE")],
                   [InlineKeyboardButton("START", f"c:{control_id}:START")]]

        control_message = await message.reply(
            f"Controller for file <code>{message.id}</code>",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        self._playing_videos[control_id] = PlayingVideo(user_id, message, control_message, self._get_user_device(user_id))

    async def _download_url(self, client, message, url, reply_message):
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                if 'youtube' in url or 'youtu.be' in url:
                    output_filename = os.path.join(tmpdir, "video1.mp4")
                    process = await asyncio.create_subprocess_shell(f"youtube-dl -v -f mp4 -o {output_filename} '{url}'")
                else:
                    output_filename = os.path.join(tmpdir, "video1")
                    process = await asyncio.create_subprocess_shell(f"you-get -O {output_filename} '{url}'")
                    output_filename = output_filename + ".mp4"

                await process.communicate()

                file_stats = os.stat(output_filename)
                await reply_message.edit_text(f"Download completed. Uploading video (size={file_stats.st_size})")
                reader = open(output_filename, mode='rb')
                video_message = await message.reply_video(reader, reply_to_message_id=message.id)

            await self._new_document(client, video_message, user_message=message)
        except Exception as e:
            await reply_message.edit_text(f"Exception thrown {e} when downloading {url}: {traceback.format_exc()}")

    async def _new_link(self, _: Client, message: Message):
        text = message.text.strip()

        result = re.search(_URL_PATTERN, text)
        if not result:
            return await message.reply("Not a supported link", reply_markup=_REMOVE_KEYBOARD)

        url = result.group(0)
        reply_message = await message.reply(f"Downloading url {url}", reply_to_message_id=message.id, disable_web_page_preview=True)
        asyncio.create_task(self._download_url(_, message, url, reply_message))
