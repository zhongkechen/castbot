import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from castbot.utils import LocalToken
from castbot.video import PlayingVideos


class ControllerRestoreRaceTest(unittest.IsolatedAsyncioTestCase):
    async def test_concurrent_callbacks_share_the_same_restored_controller(self):
        resolving = 0
        both_resolving = asyncio.Event()
        message = SimpleNamespace(id=123, media=None, message="https://youtu.be/M7lc1UVf-VE")

        async def get_message(_message_id):
            nonlocal resolving
            resolving += 1
            if resolving == 2:
                both_resolving.set()
            await both_resolving.wait()
            return message

        device = SimpleNamespace(get_device_id=lambda: "device-id")
        finders = SimpleNamespace(find_device_by_id=AsyncMock(return_value=device))
        videos = PlayingVideos(None, finders, SimpleNamespace(get_message=get_message))
        token = LocalToken(123, 9)
        control = SimpleNamespace(reply_to_message_id=123, text="Controller on device TV")

        async with asyncio.timeout(2):
            play_controller, stop_controller = await asyncio.gather(
                videos.reconstruct_playing_video(token, 1, control, device_id="device-id"),
                videos.reconstruct_playing_video(token, 1, control, device_id="device-id"),
            )

        self.assertIs(play_controller, stop_controller)
        self.assertIs(videos._playing_videos[token], play_controller)
        self.assertIs(play_controller.playing_device, device)
