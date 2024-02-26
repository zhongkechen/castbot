import abc
import logging
from functools import partial
from typing import List

from pyrogram.types import InlineKeyboardButton, CallbackQuery

from .utils import LocalToken, NoDeviceException, ActionNotSupportedException


class Button(abc.ABC):
    text: str

    def get_button(self):
        return InlineKeyboardButton(self.text, self.get_data())

    @abc.abstractmethod
    def get_data(self):
        raise NotImplementedError

    @classmethod
    @abc.abstractmethod
    async def from_data(cls, data, playing_videos, user_id, message, finders):
        raise NotImplementedError

    @abc.abstractmethod
    async def on_click(self, message: CallbackQuery):
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
        return gen_data(self.PREFIX, self.playing_video.local_token, self.text)

    @classmethod
    async def from_data(cls, data, playing_videos, user_id, message, finders):
        prefix, local_token, action = parse_data(data)
        if prefix != cls.PREFIX:
            return None
        if action not in cls.ACTION_TO_STATUS:
            return None

        playing_video = await playing_videos.reconstruct_playing_video(local_token, user_id, message)
        return cls(action, playing_video)

    async def on_click(self, message: CallbackQuery):
        try:
            action = self.text.lower()
            await getattr(self.playing_video, action)()
            await message.answer(self.ACTION_TO_STATUS[self.text])
        except NoDeviceException:
            await message.answer("Device not selected")
        except ActionNotSupportedException:
            await message.answer("Action not supported by the device")
        except Exception as ex:
            logging.exception("Failed to control the device")
            await message.answer(f"Internal error: {ex.__class__.__name__}")


class DeviceMenuButton(Button):
    PREFIX = "d"
    OLD_PREFIX = "c"
    ACTIONS = ["REFRESH", "DEVICE"]

    def __init__(self, text: str, playing_video, finders=None):
        self.playing_video = playing_video
        self.text = text
        self.finders = finders

    def get_data(self):
        return gen_data(self.PREFIX, self.playing_video.local_token, self.text)

    @classmethod
    async def from_data(cls, data, playing_videos, user_id, message, finders):
        prefix, local_token, action = parse_data(data)
        if prefix not in [cls.PREFIX, cls.OLD_PREFIX]:
            return None
        if action not in cls.ACTIONS:
            return None
        playing_video = await playing_videos.reconstruct_playing_video(local_token, user_id, message)
        return cls(action, playing_video, finders)

    async def on_click(self, message: CallbackQuery):
        assert self.finders is not None
        if self.text == "REFRESH":
            await self.finders.refresh_all_devices()
        devices = await self.finders.list_all_devices()
        await self.playing_video.send_select_device_message(devices)


class DeviceSelectButton(Button):
    PREFIX = "s"

    def __init__(self, text: str, playing_video, finders=None):
        self.playing_video = playing_video
        self.text = text
        self.finders = finders

    def get_data(self):
        return gen_data(self.PREFIX, self.playing_video.local_token, self.text)

    @classmethod
    async def from_data(cls, data, playing_videos, user_id, message, finders):
        prefix, local_token, device = parse_data(data)
        if prefix != cls.PREFIX:
            return None
        playing_video = await playing_videos.reconstruct_playing_video(local_token, user_id, message)
        return cls(device, playing_video, finders)

    async def on_click(self, message: CallbackQuery):
        assert self.finders is not None
        device = await self.finders.find_device_by_name(self.text)
        if not device:
            return await message.answer("Wrong device")

        await self.playing_video.select_device(device)


PlayButton = partial(VideoControlButton, "PLAY")
StopButton = partial(VideoControlButton, "STOP")
PauseButton = partial(VideoControlButton, "PAUSE")
ResumeButton = partial(VideoControlButton, "RESUME")
RefreshButton = partial(DeviceMenuButton, "REFRESH")
DeviceButton = partial(DeviceMenuButton, "DEVICE")


class Buttons:
    button_classes: List[Button] = [DeviceSelectButton, DeviceMenuButton, VideoControlButton]

    def __init__(self, playing_videos, finders):
        self.playing_videos = playing_videos
        self.finders = finders

    async def create_button_from_callback(self, callback_query: CallbackQuery) -> Button:
        for c in self.button_classes:
            button = await c.from_data(callback_query.data,
                                       self.playing_videos,
                                       callback_query.from_user.id,
                                       callback_query.message,
                                       self.finders)
            if button:
                return button


def gen_data(prefix, local_token, payload):
    return f"{prefix}:{local_token}:{payload}"


def parse_data(data):
    if data.count(":") == 3:
        # the old format
        prefix, message_id, token, payload = data.split(":")
        local_token = LocalToken(message_id, token)
    else:
        prefix, local_token_raw, payload = data.split(":")
        local_token = LocalToken.deserialize(local_token_raw)
    return prefix, local_token, payload
