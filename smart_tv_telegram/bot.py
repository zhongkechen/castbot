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
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from . import Config, Mtproto, Http, OnStreamClosed, DeviceFinderCollection
from .devices import Device
from .tools import secret_token, serialize_token

__all__ = [
    "Bot"
]

_URL_PATTERN = r'(http|https):\/\/([\w_-]+(?:(?:\.[\w_-]+)+))([\w.,@?^=%&:\/~+#-]*[\w@?^=%&\/~+#-])'


class UserData:
    selected_device: typing.Optional[Device] = None

    def __init__(self, selected_device):
        self.selected_device = selected_device


class NoDeviceException(Exception):
    pass


class ActionNotSupportedException(Exception):
    pass


class UnknownCallbackException(Exception):
    pass


class PlayingVideo:
    def __init__(self,
                 config: Config,
                 token: int,
                 user_id: int,
                 video_message: typing.Optional[Message] = None,
                 playing_device: typing.Optional[Device] = None,
                 control_message: typing.Optional[Message] = None,
                 link_message: typing.Optional[Message] = None):
        self._config = config
        self.token = token
        self.user_id = user_id
        self.video_message = video_message
        self.playing_device: typing.Optional[Device] = playing_device
        self.control_message = control_message
        self.link_message = link_message

    def _build_uri(self, msg_id: int, token: int) -> str:
        return f"http://{self._config.listen_host}:{self._config.listen_port}/stream/{msg_id}/{token}"

    def _gen_device_str(self):
        return f"on device <code>{html.escape(self.playing_device.get_device_name()) if self.playing_device else 'NONE'}</code>"

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
            await self.control_message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        else:
            self.control_message = await self.video_message.reply(text, reply_markup=InlineKeyboardMarkup(buttons))

    async def play(self):
        if not self.playing_device:
            raise NoDeviceException

        uri = self._build_uri(self.video_message.id, self.token)
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
            await self.playing_device.stop()
        await self.send_stopped_control_message()
        if not self.playing_device:
            raise NoDeviceException

    async def pause(self):
        if not self.playing_device:
            raise NoDeviceException
        for function in self.playing_device.get_player_functions():
            if (await function.get_name()).upper() == "PAUSE":
                await function.handle()
                return await self.send_paused_control_message()
        else:
            raise ActionNotSupportedException

    async def resume(self):
        if not self.playing_device:
            raise NoDeviceException
        for function in self.playing_device.get_player_functions():
            if (await function.get_name()).upper() == "RESUME":
                await function.handle()
                return await self.send_playing_control_message()
        else:
            raise ActionNotSupportedException

    async def select_device(self, devices):
        buttons = [[self._gen_device_button(d)] for d in devices] + [[self._gen_command_button("REFRESH")]]
        await self.create_or_update_control_message("Select a device", buttons)


def pyrogram_filename(message: Message) -> str:
    _NAMED_MEDIA_TYPES = ("document", "video", "audio", "video_note", "animation")
    try:
        return next(
            getattr(message, t, None).file_name for t in _NAMED_MEDIA_TYPES if getattr(message, t, None) is not None
        )
    except StopIteration as error:
        raise TypeError() from error


class Bot(OnStreamClosed):
    def __init__(self, mtproto: Mtproto, config: Config, http: Http, finders: DeviceFinderCollection):
        self._config = config
        self._mtproto = mtproto
        self._http = http
        self._finders = finders
        self._user_data: typing.Dict[int, UserData] = {}
        self._playing_videos: typing.Dict[int, PlayingVideo] = {}

        self._http.set_on_stream_closed_handler(self)
        self.prepare()

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

    async def _reconstruct_playing_video(self, message_id, token, callback: CallbackQuery):
        # re-construct PlayVideo when the bot is restarted
        user_id = callback.from_user.id
        control_message = callback.message
        video_message: Message = await self._mtproto.get_message(message_id)
        if control_message.reply_to_message_id != message_id:
            link_message = await self._mtproto.get_message(control_message.reply_to_message_id)
        else:
            link_message = None

        device = self._get_user_device(user_id)
        return PlayingVideo(self._config, token, user_id,
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
        elif data.startswith("c:"):
            try:
                return await self._callback_control_playback(playing_video, payload, message)
            except NoDeviceException:
                await message.answer("Device not selected")
            except ActionNotSupportedException:
                await message.answer("Action not supported by the device")
            except Exception as ex:
                traceback.print_exc()

                await message.answer(f"Unknown exception: {ex.__class__.__name__}")
        else:
            raise UnknownCallbackException

    async def _callback_control_playback(self, playing_video, action, message: CallbackQuery):
        if action in ["DEVICE", "REFRESH"]:
            if action == "REFRESH":
                await self._finders.refresh_all_devices(self._config)
            return await playing_video.select_device(await self._finders.list_all_devices(self._config))

        async with async_timeout.timeout(self._config.device_request_timeout) as timeout_context:
            if action == "PLAY":
                self._http.add_remote_token(playing_video.video_message.id, playing_video.token)
                await playing_video.play()
            elif action == "STOP":
                await playing_video.stop()
            elif action == "PAUSE":
                await playing_video.pause()
            elif action == "RESUME":
                await playing_video.resume()
        if timeout_context.expired:
            await message.answer("Timeout while communicate with the device")

    async def _callback_select_device(self, playing_video, device_name, message: CallbackQuery):
        device = await self._finders.find_device_by_name(self._config, device_name)
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

        self._playing_videos[local_token] = PlayingVideo(self._config, token, user_id,
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
            with tempfile.TemporaryDirectory() as tmpdir:
                if 'youtube' in url or 'youtu.be' in url:
                    output_filename = os.path.join(tmpdir, "video1.mp4")
                    process = await asyncio.create_subprocess_shell(
                        f"youtube-dl -v -f mp4 -o {output_filename} '{url}'")
                else:
                    output_filename = os.path.join(tmpdir, "video1")
                    process = await asyncio.create_subprocess_shell(f"you-get -O {output_filename} '{url}'")
                    output_filename = output_filename + ".mp4"

                await process.communicate()

                file_stats = os.stat(output_filename)
                await reply_message.edit_text(f"Download completed. Uploading video (size={file_stats.st_size})")
                reader = open(output_filename, mode='rb')
                video_message = await message.reply_video(reader, reply_to_message_id=message.id)
                await reply_message.edit_text(f"Upload completed.")

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
