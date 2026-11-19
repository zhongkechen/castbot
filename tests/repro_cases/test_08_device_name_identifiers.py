import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from castbot.button import Buttons, DeviceMenuButton, DeviceSelectButton, VideoControlButton, parse_data
from castbot.device import DeviceFinderCollection
from castbot.devices.vlc import VlcDevice, VlcDeviceParams
from castbot.utils import LocalToken
from castbot.video import PlayingVideo, PlayingVideos


def make_device(port):
    return VlcDevice(VlcDeviceParams({"host": "living-room", "port": port}))


def make_finders(*devices):
    collection = DeviceFinderCollection.__new__(DeviceFinderCollection)
    collection._devices = list(devices)
    collection._finders = []
    return collection


def make_callback(data, text="Select a device"):
    return SimpleNamespace(
        data=data, from_user=SimpleNamespace(id=1),
        message=SimpleNamespace(text=text, reply_to_message_id=None, edit_text=AsyncMock()),
        answer=AsyncMock(),
    )


class DeviceIdentifierTest(unittest.IsolatedAsyncioTestCase):
    def test_long_and_punctuated_labels_are_separate_from_callback_data(self):
        video = SimpleNamespace(local_token=LocalToken((1 << 63) - 1, (1 << 64) - 1))
        device = make_device(4212)
        name = "电视机" * 8 + ": TV, Living Room"
        button = DeviceSelectButton(name, video, device_id=device.get_device_id())
        self.assertEqual(button.text, name)
        self.assertEqual(parse_data(button.get_data()), ("s2", video.local_token, device.get_device_id()))
        self.assertLessEqual(len(button.get_data().encode("utf-8")), 64)

    async def test_same_display_name_selects_the_intended_endpoint(self):
        first, second = make_device(4212), make_device(4213)
        self.assertEqual(first.get_device_name(), second.get_device_name())
        self.assertNotEqual(first.get_device_id(), second.get_device_id())
        self.assertEqual(make_device(4213).get_device_id(), second.get_device_id())
        finders = make_finders(first, second)
        videos = PlayingVideos(None, finders, SimpleNamespace(get_message=AsyncMock(return_value=SimpleNamespace(id=123))))
        video = videos.new_video(LocalToken(123, 456), 1, SimpleNamespace(id=123))
        video.create_or_update_control_message = AsyncMock()

        await video.send_select_device_message([first, second])
        menu = video.create_or_update_control_message.await_args.args[1]
        selection_data = DeviceSelectButton(second.get_device_name(), video, device_id=second.get_device_id()).get_data()
        self.assertEqual(menu[1][0].text, second.get_device_name())
        callback = make_callback(selection_data)
        await Buttons(videos, finders, None).on_button_click(None, callback)
        self.assertIs(video.playing_device, second)

    async def test_controller_restores_device_id_after_restart(self):
        first, second = make_device(4212), make_device(4213)
        finders = make_finders(first, second)
        message = SimpleNamespace(id=123)
        token = LocalToken(123, 456)
        original = PlayingVideo(token, 1, None, second, message)
        for button in (VideoControlButton("PLAY", original), DeviceMenuButton("REFRESH", original)):
            with self.subTest(button=button.text):
                data = button.get_data()
                self.assertLessEqual(len(data.encode("utf-8")), 64)
                videos = PlayingVideos(None, finders, SimpleNamespace(get_message=AsyncMock(return_value=message)))
                videos.set_user_device(1, first)
                callback = make_callback(data, "Playing for file 123 on device Room, TV")
                restored = await Buttons(videos, finders, None).create_button_from_callback(callback)
                self.assertIs(restored.playing_video.playing_device, second)

    async def test_missing_explicit_identity_does_not_use_another_device(self):
        first, second = make_device(4212), make_device(4213)
        finders = make_finders(first)
        message = SimpleNamespace(id=123)
        original = PlayingVideo(LocalToken(123, 456), 1, None, second, message)
        videos = PlayingVideos(None, finders, SimpleNamespace(get_message=AsyncMock(return_value=message)))
        videos.set_user_device(1, first)
        restored = await Buttons(videos, finders, None).create_button_from_callback(
            make_callback(VideoControlButton("PLAY", original).get_data())
        )
        self.assertIsNone(restored.playing_video.playing_device)

    def test_legacy_device_labels_and_callback_formats(self):
        label = "TV: Main, Living Room"
        token = LocalToken(123, 456)
        self.assertEqual(parse_data(f"s:123:456:{label}"), ("s", token, label))
        self.assertEqual(parse_data(f"s:{token}:{label}"), ("s", token, label))
        self.assertEqual(PlayingVideo.parse_device_str(f"Playing for file 123 on device {label}"), label)
        self.assertEqual(
            PlayingVideo.parse_device_str(f"Streaming closed for file 123 on device {label}, 50.00% remains"), label,
        )

    async def test_legacy_device_menu_callback_still_restores_by_name(self):
        device = make_device(4212)
        finders = make_finders(device)
        message = SimpleNamespace(id=123)
        videos = PlayingVideos(None, finders, SimpleNamespace(get_message=AsyncMock(return_value=message)))
        callback = make_callback("c:123:456:DEVICE", f"Controller for file 123 on device {device.get_device_name()}")
        restored = await Buttons(videos, finders, None).create_button_from_callback(callback)
        self.assertIsInstance(restored, DeviceMenuButton)
        self.assertIs(restored.playing_video.playing_device, device)
