import abc
import asyncio
import enum
import functools
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
from pyrogram.types import ReplyKeyboardRemove, Message, KeyboardButton, ReplyKeyboardMarkup, CallbackQuery, \
    InlineKeyboardMarkup, InlineKeyboardButton

from . import Config, Mtproto, Http, OnStreamClosed, DeviceFinderCollection
from .devices import Device, DevicePlayerFunction
from .tools import build_uri, pyrogram_filename, secret_token

__all__ = [
    "Bot"
]

_REMOVE_KEYBOARD = ReplyKeyboardRemove()
_CANCEL_BUTTON = "^Cancel"
_URL_PATTERN = r'(http|https):\/\/([\w_-]+(?:(?:\.[\w_-]+)+))([\w.,@?^=%&:\/~+#-]*[\w@?^=%&\/~+#-])'


class States(enum.Enum):
    NOTHING = enum.auto()
    SELECT = enum.auto()
    DOWNLOAD = enum.auto()


class StateData(abc.ABC):
    @abc.abstractmethod
    def get_associated_state(self) -> States:
        raise NotImplementedError


class SelectStateData(StateData):
    msg_id: int
    filename: str
    devices: typing.List[Device]

    def get_associated_state(self) -> States:
        return States.SELECT

    def __init__(self, msg_id: int, filename: str, devices: typing.List[Device]):
        self.msg_id = msg_id
        self.filename = filename
        self.devices = devices


class DownloadStateData(StateData):
    def get_associated_state(self) -> States:
        return States.DOWNLOAD

    def __init__(self, msg_id: int, url: str, task: asyncio.Task):
        self.msg_id = msg_id
        self.url = url
        self.task = task


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


class TelegramStateMachine:
    _states: typing.Dict[int, typing.Tuple[States, typing.Union[bool, StateData]]]

    def __init__(self):
        self._states = {}

    def get_state(self, message: Message) -> typing.Tuple[States, typing.Union[bool, StateData]]:
        user_id = message.from_user.id

        if user_id in self._states:
            return self._states[user_id]

        return States.NOTHING, False

    def set_state(self, user_id: int, video_message: Message, state: States, data: typing.Union[bool, StateData]) -> bool:
        if isinstance(data, bool) or data.get_associated_state() == state:
            self._states[user_id] = (state, data)
            return True

        raise TypeError()


class UserData:
    selected_device: typing.Optional[Device] = None

    def __init__(self, selected_device):
        self.selected_device = selected_device


class Bot:
    _config: Config
    _state_machine: TelegramStateMachine
    _mtproto: Mtproto
    _http: Http
    _finders: DeviceFinderCollection
    _functions: typing.Dict[int, typing.Dict[int, DevicePlayerFunction]]
    _devices: typing.Dict[int, Device]
    _user_data: typing.Dict[int, UserData]

    def __init__(self, mtproto: Mtproto, config: Config, http: Http, finders: DeviceFinderCollection):
        self._config = config
        self._mtproto = mtproto
        self._http = http
        self._finders = finders
        self._state_machine = TelegramStateMachine()
        self._functions = {}
        self._devices = {}
        self._all_devices = []
        self._user_data = {}

        self._http.set_on_stream_closed_handler(self.get_on_stream_closed())
        self.prepare()

    def get_on_stream_closed(self) -> OnStreamClosed:
        return OnStreamClosedHandler(self._mtproto, self._functions, self._devices)

    def prepare(self):
        admin_filter = filters.chat(self._config.admins) & filters.private
        self._mtproto.register(MessageHandler(self._device_selector, filters.command("select_device") & admin_filter))

        state_filter = create(lambda _, __, m: self._state_machine.get_state(m)[0] == States.NOTHING)
        self._mtproto.register(MessageHandler(self._new_document, filters.document & admin_filter & state_filter))
        self._mtproto.register(MessageHandler(self._new_document, filters.video & admin_filter))
        self._mtproto.register(MessageHandler(self._new_document, filters.audio & admin_filter))
        self._mtproto.register(MessageHandler(self._new_document, filters.animation & admin_filter))
        self._mtproto.register(MessageHandler(self._new_document, filters.voice & admin_filter))
        self._mtproto.register(MessageHandler(self._new_document, filters.video_note & admin_filter))
        self._mtproto.register(MessageHandler(self._new_link, filters.text & admin_filter & state_filter))

        admin_filter_inline = create(lambda _, __, m: m.from_user.id in self._config.admins)
        self._mtproto.register(CallbackQueryHandler(self._callback_handler, admin_filter_inline))

        state_filter = create(lambda _, __, m: self._state_machine.get_state(m)[0] == States.SELECT)
        self._mtproto.register(MessageHandler(self._select_device, filters.text & admin_filter & state_filter))

    async def _callback_handler(self, _: Client, message: CallbackQuery):
        data = message.data

        if data.startswith("s:"):
            return await self._select_device(message)

        try:
            data = int(data)
        except ValueError:
            await message.answer("wrong callback")

        try:
            device_function = next(
                f_v
                for f in self._functions.values()
                for f_k, f_v in f.items()
                if f_k == data
            )
        except StopIteration:
            await message.answer("stream closed")
            return

        if not await device_function.is_enabled(self._config):
            await message.answer("function not enabled")
            return

        with async_timeout.timeout(self._config.device_request_timeout) as timeout_context:
            await device_function.handle()

        if timeout_context.expired:
            await message.answer("request timeout")
        else:
            await message.answer("done")

    async def _select_device(self, message: CallbackQuery):
        data = message.data
        device_name = data.split(":", 1)[1]
        try:
            device = next(
                device
                for device in self._all_devices
                if repr(device) == device_name
            )
        except StopIteration:
            await message.answer("Wrong device")
            return

        self._user_data[message.from_user.id] = UserData(device)
        await message.answer("Selected " + device_name)

    async def _device_selector(self, client: Client, message: Message):
        self._all_devices = []

        for finder in self._finders.get_finders(self._config):
            with async_timeout.timeout(self._config.device_request_timeout + 1):
                self._all_devices.extend(await finder.find(self._config))

        if self._all_devices:
            buttons = [[InlineKeyboardButton(repr(device), "s:" + repr(device))] for device in self._all_devices]
            await message.reply("Select a device", reply_markup=InlineKeyboardMarkup(buttons), reply_to_message_id=message.id)
        else:
            await message.reply("Supported devices not found in the network")

    async def _new_document(self, _: Client, message: Message, user_message=None):
        user_id = (user_message or message).from_user.id
        user_data = self._user_data.get(user_id)
        reply = message.reply
        if not user_data or not user_data.selected_device:
            await reply("No device selected")
            return

        device = user_data.selected_device
        msg_id = message.id
        async with async_timeout.timeout(self._config.device_request_timeout) as timeout_context:
            token = secret_token()
            local_token = self._http.add_remote_token(msg_id, token)
            uri = build_uri(self._config, msg_id, token)

            try:
                filename = pyrogram_filename(message)
            except TypeError:
                filename = "None"

            # noinspection PyBroadException
            try:
                await device.stop()
                await device.play(uri, str(filename), local_token)

            except Exception as ex:
                traceback.print_exc()

                await reply(
                    "Error while communicate with the device:\n\n"
                    f"<code>{html.escape(str(ex))}</code>"
                )

            else:
                self._devices[local_token] = device
                physical_functions = device.get_player_functions()
                functions = self._functions[local_token] = {}

                if physical_functions:
                    buttons = []

                    for function in physical_functions:
                        function_id = secret_token()
                        function_name = await function.get_name()
                        button = InlineKeyboardButton(function_name, str(function_id))
                        functions[function_id] = function
                        buttons.append([button])

                    await message.reply(
                        f"Device <code>{html.escape(device.get_device_name())}</code>\n"
                        f"controller for file <code>{msg_id}</code>",
                        reply_markup=InlineKeyboardMarkup(buttons)
                    )

                    stub_message = await reply("stub")
                    await stub_message.delete()

                else:
                    await reply(f"Playing file <code>{msg_id}</code>")

        if timeout_context.expired:
            await reply("Timeout while communicate with the device")


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
            self._state_machine.set_state(message.from_user.id, message, States.NOTHING, False)
            await reply_message.edit_text(f"Exception thrown {e} when downloading {url}: {traceback.format_exc()}")

    async def _new_link(self, _: Client, message: Message):
        state, state_data = self._state_machine.get_state(message)
        if state == States.DOWNLOAD:
            return await message.reply("Still downloading link", reply_markup=_REMOVE_KEYBOARD)

        text = message.text.strip()

        result = re.search(_URL_PATTERN, text)
        if not result:
            return await message.reply("Not a supported link", reply_markup=_REMOVE_KEYBOARD)

        url = result.group(0)
        reply_message = await message.reply(f"Downloading url {url}", reply_to_message_id=message.id, disable_web_page_preview=True)
        task = asyncio.create_task(self._download_url(_, message, url, reply_message))
        self._state_machine.set_state(message.from_user.id, message, States.DOWNLOAD, DownloadStateData(message.id, url, task))
