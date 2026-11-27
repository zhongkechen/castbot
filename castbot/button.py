import abc
import logging
from functools import partial
from typing import List

from pyrogram import Client
from pyrogram.types import InlineKeyboardButton, CallbackQuery

from .downloader import Downloader
from .utils import ActionNotSupportedException, DeviceControlError, LocalToken, NoDeviceException
from .utils import UnknownCallbackException
from .youtube import YouTubeRelayError


class Context:
    def __init__(self, callback_query: CallbackQuery, playing_videos, finders, downloader: Downloader):
        self.callback_query = callback_query
        self.playing_videos = playing_videos
        self.finders = finders
        self.downloader = downloader

    @property
    def from_user(self):
        return self.callback_query.from_user.id

    @property
    def message(self):
        return self.callback_query.message


class Button(abc.ABC):
    PREFIX: str
    text: str

    @classmethod
    def matches(cls, data: str) -> bool:
        return data.startswith(cls.PREFIX + ":")

    def get_button(self):
        return InlineKeyboardButton(self.text, callback_data=self.get_data())

    @abc.abstractmethod
    def get_data(self):
        raise NotImplementedError

    @classmethod
    @abc.abstractmethod
    async def from_data(cls, data, context: Context):
        raise NotImplementedError

    @abc.abstractmethod
    async def on_click(self, callback_query: CallbackQuery):
        raise NotImplementedError


class VideoControlButton(Button):
    PREFIX = "c"
    ACTION_TO_STATUS = {
        "PLAY": "Playing",
        "STOP": "Stopped",
        "PAUSE": "Paused",
        "RESUME": "Resumed",
    }

    def __init__(self, text: str, playing_video):
        assert text in self.ACTION_TO_STATUS
        self.text = text
        self.playing_video = playing_video

    def get_data(self):
        return gen_control_data(self.PREFIX, self.playing_video, self.text)

    @classmethod
    async def from_data(cls, data, context: Context):
        prefix, local_token, payload = parse_data(data)
        action, _, device_id = payload.partition("~")
        if prefix != cls.PREFIX:
            return None
        if action not in cls.ACTION_TO_STATUS:
            return None

        playing_video = await context.playing_videos.reconstruct_playing_video(local_token,
                                                                               context.from_user,
                                                                               context.message,
                                                                               device_id=device_id or None)
        return cls(action, playing_video)

    async def on_click(self, callback_query: CallbackQuery):
        try:
            action = self.text.lower()
            await getattr(self.playing_video, action)()
            await callback_query.answer(self.ACTION_TO_STATUS[self.text])
        except NoDeviceException:
            await callback_query.answer("Device not selected")
        except ActionNotSupportedException:
            await callback_query.answer("Action not supported by the device")
        except YouTubeRelayError as error:
            await callback_query.answer(str(error), show_alert=True)
        except DeviceControlError as error:
            await callback_query.answer(f"Device command failed: {error}")
        except Exception as ex:
            logging.exception("Failed to control the device")
            await callback_query.answer(f"Internal error: {ex.__class__.__name__}")


class DeviceMenuButton(Button):
    PREFIX = "d"
    OLD_PREFIX = "c"
    ACTIONS = ["REFRESH", "DEVICE"]

    @classmethod
    def matches(cls, data: str) -> bool:
        return super().matches(data) or (
            data.startswith(cls.OLD_PREFIX + ":") and data.rsplit(":", 1)[-1] in cls.ACTIONS
        )

    def __init__(self, text: str, playing_video, finders=None):
        self.playing_video = playing_video
        self.text = text
        self.finders = finders

    def get_data(self):
        return gen_control_data(self.PREFIX, self.playing_video, self.text)

    @classmethod
    async def from_data(cls, data, context: Context):
        prefix, local_token, payload = parse_data(data)
        action, _, device_id = payload.partition("~")
        if prefix not in [cls.PREFIX, cls.OLD_PREFIX]:
            return None
        if action not in cls.ACTIONS:
            return None
        playing_video = await context.playing_videos.reconstruct_playing_video(local_token,
                                                                               context.from_user,
                                                                               context.message,
                                                                               device_id=device_id or None)
        return cls(action, playing_video, context.finders)

    async def on_click(self, callback_query: CallbackQuery):
        assert self.finders is not None
        await callback_query.answer()
        if self.text == "REFRESH":
            await self.finders.refresh_all_devices()
        devices = await self.finders.list_all_devices()
        await self.playing_video.send_select_device_message(devices)


class DeviceSelectButton(Button):
    PREFIX = "s2"
    OLD_PREFIX = "s"

    @classmethod
    def matches(cls, data: str) -> bool:
        return super().matches(data) or data.startswith(cls.OLD_PREFIX + ":")

    def __init__(self, text: str, playing_video, finders=None, *, device_id=None):
        self.playing_video = playing_video
        self.text = text
        self.finders = finders
        self.device_id = device_id

    def get_data(self):
        if self.device_id is None:
            return gen_data(self.OLD_PREFIX, self.playing_video.local_token, self.text)
        return gen_data(self.PREFIX, self.playing_video.local_token, self.device_id)

    @classmethod
    async def from_data(cls, data, context):
        prefix, local_token, device = parse_data(data)
        if prefix not in (cls.PREFIX, cls.OLD_PREFIX):
            return None
        playing_video = await context.playing_videos.reconstruct_playing_video(local_token,
                                                                               context.from_user,
                                                                               context.message)
        return cls(device, playing_video, context.finders, device_id=device if prefix == cls.PREFIX else None)

    async def on_click(self, callback_query: CallbackQuery):
        assert self.finders is not None
        if self.device_id is None:
            device = await self.finders.find_device_by_name(self.text)
        else:
            device = await self.finders.find_device_by_id(self.device_id)
        if not device:
            return await callback_query.answer("Wrong device")

        await callback_query.answer()
        await self.playing_video.select_device(device)


class RetryDownloadButton(Button):
    PREFIX = "r"

    def __init__(self, text: str, downloader=None):
        self.text = text
        self.downloader = downloader

    def get_data(self):
        return ":".join([self.PREFIX, self.text])

    @classmethod
    async def from_data(cls, data, context: Context):
        prefix, text = data.split(":")
        assert prefix == cls.PREFIX
        return cls(text, context.downloader)

    async def on_click(self, callback_query: CallbackQuery):
        url = self.downloader.parse_link_message(callback_query.message.reply_to_message)
        if url:
            await callback_query.answer()
            await self.downloader.download_url(callback_query.message.reply_to_message, url, callback_query.message)
        else:
            await callback_query.answer("Url no longer exists")


class StreamButton(Button):
    PREFIX = "q"

    def __init__(self, playing_video, text="STREAM", action="menu"):
        self.playing_video = playing_video
        self.text = text
        self.action = action

    def get_data(self):
        data = gen_control_data(self.PREFIX, self.playing_video, self.action)
        if len(data.encode("utf8")) <= 64:
            return data
        return gen_data(self.PREFIX, self.playing_video.local_token, self.action)

    @classmethod
    async def from_data(cls, data, context):
        _, local_token, payload = parse_data(data)
        action, _, device_id = payload.partition("~")
        if action not in {"menu", "back"} and not action.startswith("pick"):
            return None
        video = await context.playing_videos.reconstruct_playing_video(
            local_token, context.from_user, context.message, device_id=device_id or None,
        )
        return cls(video, action=action) if video.is_youtube else None

    async def on_click(self, callback_query: CallbackQuery):
        await callback_query.answer()
        await self.playing_video.handle_stream_selection(self.action)


PlayButton = partial(VideoControlButton, "PLAY")
StopButton = partial(VideoControlButton, "STOP")
PauseButton = partial(VideoControlButton, "PAUSE")
ResumeButton = partial(VideoControlButton, "RESUME")
RefreshButton = partial(DeviceMenuButton, "REFRESH")
DeviceButton = partial(DeviceMenuButton, "DEVICE")
RetryButton = partial(RetryDownloadButton, "RETRY")


class Buttons:
    button_classes: List[Button] = [
        DeviceSelectButton, DeviceMenuButton, VideoControlButton, RetryDownloadButton, StreamButton,
    ]

    def __init__(self, playing_videos, finders, downloader):
        self.playing_videos = playing_videos
        self.finders = finders
        self.downloader = downloader

    async def create_button_from_callback(self, callback_query: CallbackQuery) -> Button | None:
        context = Context(callback_query, self.playing_videos, self.finders, self.downloader)
        for c in self.button_classes:
            if c.matches(callback_query.data):
                return await c.from_data(callback_query.data, context)
        return None

    async def on_button_click(self, _: Client, callback_query: CallbackQuery):
        button = await self.create_button_from_callback(callback_query)
        if not button:
            raise UnknownCallbackException

        await button.on_click(callback_query)


def gen_data(prefix, local_token, payload):
    return f"{prefix}:{local_token}:{payload}"


def gen_control_data(prefix, video, action):
    device = video.playing_device
    payload = f"{action}~{device.get_device_id()}" if device else action
    return gen_data(prefix, video.local_token, payload)


def parse_data(data):
    prefix, token, payload = data.split(":", 2)
    # Legacy callbacks used a separate decimal message ID and token.
    # Packed tokens for positive message IDs occupy at least 17 hex digits.
    legacy_token, separator, legacy_payload = payload.partition(":")
    if len(token) < 17 and token.isdecimal() and separator and legacy_token.isdecimal():
        return prefix, LocalToken(token, legacy_token), legacy_payload
    return prefix, LocalToken.deserialize(token), payload
