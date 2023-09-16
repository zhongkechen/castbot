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

    def set_state(self, message: Message, state: States, data: typing.Union[bool, StateData]) -> bool:
        if isinstance(data, bool) or data.get_associated_state() == state:
            self._states[message.from_user.id] = (state, data)
            return True

        raise TypeError()


class Bot:
    _config: Config
    _state_machine: TelegramStateMachine
    _mtproto: Mtproto
    _http: Http
    _finders: DeviceFinderCollection
    _functions: typing.Dict[int, typing.Dict[int, DevicePlayerFunction]]
    _devices: typing.Dict[int, Device]

    def __init__(self, mtproto: Mtproto, config: Config, http: Http, finders: DeviceFinderCollection):
        self._config = config
        self._mtproto = mtproto
        self._http = http
        self._finders = finders
        self._state_machine = TelegramStateMachine()
        self._functions = {}
        self._devices = {}

    def get_on_stream_closed(self) -> OnStreamClosed:
        return OnStreamClosedHandler(self._mtproto, self._functions, self._devices)

    def prepare(self):
        admin_filter = filters.chat(self._config.admins) & filters.private
        state_filter = create(lambda _, __, m: self._state_machine.get_state(m)[0] == States.NOTHING)
        self._mtproto.register(MessageHandler(self._new_document, filters.document & admin_filter & state_filter))
        self._mtproto.register(MessageHandler(self._new_document, filters.video & admin_filter))
        self._mtproto.register(MessageHandler(self._new_document, filters.audio & admin_filter))
        self._mtproto.register(MessageHandler(self._new_document, filters.animation & admin_filter))
        self._mtproto.register(MessageHandler(self._new_document, filters.voice & admin_filter))
        self._mtproto.register(MessageHandler(self._new_document, filters.video_note & admin_filter))
        self._mtproto.register(MessageHandler(self._new_link, filters.text & admin_filter & state_filter))

        admin_filter_inline = create(lambda _, __, m: m.from_user.id in self._config.admins)
        self._mtproto.register(CallbackQueryHandler(self._device_player_function, admin_filter_inline))

        state_filter = create(lambda _, __, m: self._state_machine.get_state(m)[0] == States.SELECT)
        self._mtproto.register(MessageHandler(self._select_device, filters.text & admin_filter & state_filter))

    async def _device_player_function(self, _: Client, message: CallbackQuery):
        data = message.data

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

    async def _select_device(self, _: Client, message: Message):
        data: SelectStateData
        _, data = self._state_machine.get_state(message)

        self._state_machine.set_state(message, States.NOTHING, False)
        reply = functools.partial(message.reply, reply_markup=_REMOVE_KEYBOARD)

        if message.text == _CANCEL_BUTTON:
            await reply("Cancelled")
            return

        try:
            device = next(
                device
                for device in data.devices
                if repr(device) == message.text
            )
        except StopIteration:
            await reply("Wrong device")
            return

        async with async_timeout.timeout(self._config.device_request_timeout) as timeout_context:
            token = secret_token()
            local_token = self._http.add_remote_token(data.msg_id, token)
            uri = build_uri(self._config, data.msg_id, token)

            # noinspection PyBroadException
            try:
                await device.stop()
                await device.play(uri, data.filename, local_token)

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
                        f"controller for file <code>{data.msg_id}</code>",
                        reply_markup=InlineKeyboardMarkup(buttons)
                    )

                    stub_message = await reply("stub")
                    await stub_message.delete()

                else:
                    await reply(f"Playing file <code>{data.msg_id}</code>")

        if timeout_context.expired:
            await reply("Timeout while communicate with the device")

    async def _new_document(self, _: Client, message: Message, user_message = None):
        devices = []

        for finder in self._finders.get_finders(self._config):
            with async_timeout.timeout(self._config.device_request_timeout + 1):
                devices.extend(await finder.find(self._config))

        if devices:
            try:
                filename = pyrogram_filename(message)
            except TypeError:
                filename = "None"

            self._state_machine.set_state(
                user_message or message,
                States.SELECT,
                SelectStateData(
                    message.id,
                    str(filename),
                    devices.copy()
                )
            )

            buttons = [[KeyboardButton(repr(device))] for device in devices]
            buttons.append([KeyboardButton(_CANCEL_BUTTON)])
            markup = ReplyKeyboardMarkup(buttons, one_time_keyboard=True)
            await message.reply("Select a device", reply_markup=markup)

        else:
            await message.reply("Supported devices not found in the network", reply_markup=_REMOVE_KEYBOARD)

    async def _download_url(self, client, message, url):
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
                await message.reply(f"Download completed. Uploading video (size={file_stats.st_size})")
                reader = open(output_filename, mode='rb')
                video_message = await message.reply_video(reader)

            await self._new_document(client, video_message, user_message=message)
        except Exception as e:
            self._state_machine.set_state(message, States.NOTHING, False)
            await message.reply(f"Exception thrown {e} when downloading {url}: {traceback.format_exc()}")

    async def _new_link(self, _: Client, message: Message):
        state, state_data = self._state_machine.get_state(message)
        if state == States.DOWNLOAD:
            return await message.reply("Still downloading link", reply_markup=_REMOVE_KEYBOARD)

        text = message.text.strip()

        result = re.search(_URL_PATTERN, text)
        if not result:
            return await message.reply("Not a supported link", reply_markup=_REMOVE_KEYBOARD)

        url = result.group(0)
        task = asyncio.create_task(self._download_url(_, message, url))
        self._state_machine.set_state(message, States.DOWNLOAD, DownloadStateData(message.id, url, task))
        await message.reply(f"Downloading url {url}", reply_markup=_REMOVE_KEYBOARD, disable_web_page_preview=True)

