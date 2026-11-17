"""A passing case confirms callbacks stay unanswered after success; it is not a fix."""

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from castbot.button import DeviceMenuButton, DeviceSelectButton, RetryDownloadButton


class UnansweredCallbackReproduction(unittest.IsolatedAsyncioTestCase):
    async def test_device_menu_success_never_answers_callback(self):
        for action in ["DEVICE", "REFRESH"]:
            with self.subTest(action=action):
                devices = [SimpleNamespace(name="dummy device")]
                finder = SimpleNamespace(
                    list_all_devices=AsyncMock(return_value=devices), refresh_all_devices=AsyncMock()
                )
                video = SimpleNamespace(send_select_device_message=AsyncMock())
                callback = SimpleNamespace(answer=AsyncMock())

                await DeviceMenuButton(action, video, finder).on_click(callback)

                video.send_select_device_message.assert_awaited_once_with(devices)
                if action == "REFRESH":
                    finder.refresh_all_devices.assert_awaited_once()
                callback.answer.assert_not_awaited()
        print("Observed: DEVICE and REFRESH finish displaying the device menu without answering the callback.")

    async def test_device_selection_success_never_answers_callback(self):
        device = SimpleNamespace(name="dummy device")
        finder = SimpleNamespace(find_device_by_name=AsyncMock(return_value=device))
        video = SimpleNamespace(select_device=AsyncMock())
        callback = SimpleNamespace(answer=AsyncMock())

        await DeviceSelectButton("dummy device", video, finder).on_click(callback)

        video.select_device.assert_awaited_once_with(device)
        callback.answer.assert_not_awaited()
        print("Observed: successful device selection leaves the callback unanswered.")

    async def test_download_retry_success_never_answers_callback(self):
        source_message = SimpleNamespace(text="https://media.invalid/video.mp4")
        reply_message = SimpleNamespace(reply_to_message=source_message)
        callback = SimpleNamespace(answer=AsyncMock(), message=reply_message)
        downloader = SimpleNamespace(
            parse_link_message=Mock(return_value="https://media.invalid/video.mp4"),
            download_url=AsyncMock(),
        )

        await RetryDownloadButton("RETRY", downloader).on_click(callback)

        downloader.download_url.assert_awaited_once_with(
            source_message, "https://media.invalid/video.mp4", reply_message
        )
        callback.answer.assert_not_awaited()
        print("Observed: a completed download retry leaves the callback unanswered.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
