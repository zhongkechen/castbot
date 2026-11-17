"""A passing case confirms failed control is announced as Playing; it is not a fix."""

import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import castbot.devices.vlc as vlc_module
import castbot.devices.xbmc as xbmc_module
from castbot.button import VideoControlButton
from castbot.utils import LocalToken
from castbot.video import PlayingVideo


def playback_controller(device):
    control = SimpleNamespace(edit_text=AsyncMock())
    video = PlayingVideo(
        local_token=LocalToken(123, 9),
        user_id=99,
        playing_videos=SimpleNamespace(add_to_http=lambda _: "http://media.invalid/stream/123/9"),
        playing_device=device,
        video_message=SimpleNamespace(id=123, document=SimpleNamespace(file_name="dummy.mp4")),
        control_message=control,
    )
    return video, control, SimpleNamespace(answer=AsyncMock())


class FailedControlReproduction(unittest.IsolatedAsyncioTestCase):
    async def test_kodi_401_still_announces_playing(self):
        calls = []

        class UnauthorizedSession:
            def __init__(self, **_kwargs):
                pass

            async def post(self, _url, data):
                calls.append(json.loads(data)["method"])
                return SimpleNamespace(status=401, close=Mock())

            async def close(self):
                pass

        kodi = xbmc_module.XbmcDevice(
            xbmc_module.XbmcDeviceParams(
                {"host": "device.invalid", "port": 8080, "username": "dummy-user", "password": "dummy-password"}
            )
        )
        video, control, callback = playback_controller(kodi)
        with patch.object(xbmc_module.aiohttp, "ClientSession", UnauthorizedSession):
            with patch.object(xbmc_module._LOGGER, "error"):
                await VideoControlButton("PLAY", video).on_click(callback)

        self.assertEqual(calls, ["Player.GetActivePlayers", "Playlist.Clear", "Playlist.Add", "Player.Open"])
        self.assertTrue(control.edit_text.await_args.args[0].startswith("Playing "))
        callback.answer.assert_awaited_once_with("Playing")
        print("Observed: all four Kodi RPCs return 401, but the controller and callback announce Playing.")

    async def test_vlc_rejected_authentication_still_announces_playing(self):
        writers = []

        async def rejected_connection(*_args):
            writer = SimpleNamespace(write=Mock(), drain=AsyncMock(), close=Mock())
            writers.append(writer)
            reader = SimpleNamespace(
                read=AsyncMock(side_effect=[b"Password: " + vlc_module._AUTH_MAGIC, b"Wrong password"])
            )
            return reader, writer

        vlc = vlc_module.VlcDevice(
            vlc_module.VlcDeviceParams({"host": "device.invalid", "port": 4212, "password": "dummy-password"})
        )
        video, control, callback = playback_controller(vlc)
        with patch.object(vlc_module.asyncio, "open_connection", rejected_connection):
            with patch.object(vlc_module._LOGGER, "error"):
                await VideoControlButton("PLAY", video).on_click(callback)

        self.assertEqual(len(writers), 3)
        for writer in writers:
            writer.write.assert_called_once_with(b"dummy-password" + vlc_module._EOF)
            writer.close.assert_called_once()
        self.assertTrue(control.edit_text.await_args.args[0].startswith("Playing "))
        callback.answer.assert_awaited_once_with("Playing")
        print("Observed: all three VLC connections reject authentication, but the controller announces Playing.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
