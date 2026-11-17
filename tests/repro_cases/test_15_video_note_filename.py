"""A passing case confirms the current VideoNote playback defect; it is not a fix."""

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from pyrogram.types import VideoNote

from castbot.utils import LocalToken
from castbot.video import PlayingVideo


class VideoNoteReproduction(unittest.IsolatedAsyncioTestCase):
    async def test_real_video_note_fails_before_device_playback(self):
        note = VideoNote(file_id="dummy-id", file_unique_id="dummy-unique-id", length=64, duration=10)
        device = SimpleNamespace(stop=AsyncMock(), play=AsyncMock())
        controller = SimpleNamespace(edit_text=AsyncMock())
        video = PlayingVideo(
            local_token=LocalToken(123, 9),
            user_id=99,
            playing_videos=SimpleNamespace(add_to_http=lambda _: "http://media.invalid/stream/123/9"),
            playing_device=device,
            video_message=SimpleNamespace(id=123, video_note=note),
            control_message=controller,
        )

        with self.assertRaisesRegex(AttributeError, "file_name"):
            await video.play()

        device.stop.assert_not_awaited()
        device.play.assert_not_awaited()
        controller.edit_text.assert_not_awaited()
        print("Observed: real VideoNote raises AttributeError(file_name) before any playback command.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
