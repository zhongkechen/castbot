"""Verify filename handling for circular Telegram videos."""

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from pyrogram.types import VideoNote

from castbot.utils import LocalToken
from castbot.video import PlayingVideo


class VideoNoteTest(unittest.IsolatedAsyncioTestCase):
    async def test_real_video_note_reaches_device_with_fallback_filename(self):
        note = VideoNote(file_id="dummy-id", file_unique_id="dummy-unique-id", length=64, duration=10)
        device = SimpleNamespace(
            stop=AsyncMock(), play=AsyncMock(),
            get_device_id=lambda: "device-id", get_device_name=lambda: "TV",
        )
        controller = SimpleNamespace(edit_text=AsyncMock())
        video = PlayingVideo(
            local_token=LocalToken(123, 9),
            user_id=99,
            playing_videos=SimpleNamespace(
                add_to_http=lambda _: "http://media.invalid/stream/123/9", interrupt_playlist=AsyncMock(),
            ),
            playing_device=device,
            video_message=SimpleNamespace(id=123, video_note=note),
            control_message=controller,
        )

        await video.play()

        device.stop.assert_awaited_once_with()
        device.play.assert_awaited_once_with(
            "http://media.invalid/stream/123/9", "video_note_123.mp4", video.local_token,
        )
        controller.edit_text.assert_awaited_once()

    def test_regular_video_keeps_its_filename(self):
        message = SimpleNamespace(id=123, video=SimpleNamespace(file_name="original.mp4"))
        self.assertEqual(PlayingVideo.pyrogram_filename(message), "original.mp4")


if __name__ == "__main__":
    unittest.main(verbosity=2)
