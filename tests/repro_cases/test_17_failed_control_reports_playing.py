"""A PLAY callback reports errors from Kodi and VLC."""

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
        playing_videos=SimpleNamespace(
            add_to_http=Mock(return_value="http://media.invalid/stream/123/9"), interrupt_playlist=AsyncMock(),
        ),
        playing_device=device,
        video_message=SimpleNamespace(id=123, document=SimpleNamespace(file_name="dummy.mp4")),
        control_message=control,
    )
    return video, control, SimpleNamespace(answer=AsyncMock())


class FailedControlTest(unittest.IsolatedAsyncioTestCase):
    async def kodi_play(self, http_status, json_replies):
        calls = []
        replies = iter(json_replies)
        responses = []
        session_closed = AsyncMock()

        class FakeSession:
            def __init__(self, **_kwargs):
                self.close = session_closed

            async def post(self, _url, data):
                calls.append(json.loads(data)["method"])
                response = SimpleNamespace(status=http_status, close=Mock())
                if http_status == 200:
                    response.json = AsyncMock(return_value=next(replies))
                responses.append(response)
                return response

        kodi = xbmc_module.XbmcDevice(
            xbmc_module.XbmcDeviceParams(
                {"host": "device.invalid", "port": 8080, "username": "dummy-user", "password": "dummy-password"}
            )
        )
        video, control, callback = playback_controller(kodi)
        with patch.object(xbmc_module.aiohttp, "ClientSession", FakeSession):
            await VideoControlButton("PLAY", video).on_click(callback)

        self.assertEqual(session_closed.await_count, len(calls))
        for response in responses:
            response.close.assert_called_once()
        return video, control, callback, calls

    async def test_kodi_401_aborts_play(self):
        video, control, callback, calls = await self.kodi_play(401, [])
        self.assertEqual(calls, ["Player.GetActivePlayers"])
        video.playing_videos.add_to_http.assert_not_called()
        control.edit_text.assert_not_awaited()
        callback.answer.assert_awaited_once_with("Device command failed: Kodi returned HTTP 401")

    async def test_kodi_rpc_error_aborts_play(self):
        _, control, callback, calls = await self.kodi_play(200, [
            {"result": []}, {"result": "OK"}, {"error": {"message": "Device rejected item"}},
        ])
        self.assertEqual(calls, ["Player.GetActivePlayers", "Playlist.Clear", "Playlist.Add"])
        control.edit_text.assert_not_awaited()
        callback.answer.assert_awaited_once_with("Device command failed: Kodi returned a JSON-RPC error")

    async def test_successful_kodi_control_still_announces_playing(self):
        _, control, callback, calls = await self.kodi_play(200, [
            {"result": []}, {"result": "OK"}, {"result": "OK"}, {"result": "OK"},
        ])
        self.assertEqual(calls, ["Player.GetActivePlayers", "Playlist.Clear", "Playlist.Add", "Player.Open"])
        self.assertTrue(control.edit_text.await_args.args[0].startswith("Playing "))
        callback.answer.assert_awaited_once_with("Playing")

    async def test_vlc_rejected_authentication_aborts_play(self):
        writer = SimpleNamespace(write=Mock(), drain=AsyncMock(), close=Mock())
        reader = SimpleNamespace(
            read=AsyncMock(side_effect=[b"Password: " + vlc_module._AUTH_MAGIC, b"Wrong password"])
        )
        vlc = vlc_module.VlcDevice(
            vlc_module.VlcDeviceParams({"host": "device.invalid", "port": 4212, "password": "dummy-password"})
        )
        video, control, callback = playback_controller(vlc)
        connection = AsyncMock(return_value=(reader, writer))
        with patch.object(vlc_module.asyncio, "open_connection", connection):
            await VideoControlButton("PLAY", video).on_click(callback)

        connection.assert_awaited_once()
        writer.write.assert_called_once_with(b"dummy-password" + vlc_module._EOF)
        writer.close.assert_called_once()
        video.playing_videos.add_to_http.assert_not_called()
        control.edit_text.assert_not_awaited()
        callback.answer.assert_awaited_once_with("Device command failed: VLC rejected authentication")


if __name__ == "__main__":
    unittest.main(verbosity=2)
