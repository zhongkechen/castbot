"""Verify Telegram callbacks are answered before follow-up work."""

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from castbot.button import DeviceMenuButton, DeviceSelectButton, RetryDownloadButton


class CallbackAnswerTest(unittest.IsolatedAsyncioTestCase):
    async def test_device_menu_acknowledges_success(self):
        for action in ["DEVICE", "REFRESH"]:
            with self.subTest(action=action):
                devices = [SimpleNamespace(name="dummy device")]
                finder = SimpleNamespace(
                    list_all_devices=AsyncMock(return_value=devices), refresh_all_devices=AsyncMock()
                )
                callback = SimpleNamespace(answer=AsyncMock())

                async def send_menu(_devices):
                    callback.answer.assert_awaited_once_with()

                video = SimpleNamespace(send_select_device_message=AsyncMock(side_effect=send_menu))

                await DeviceMenuButton(action, video, finder).on_click(callback)

                video.send_select_device_message.assert_awaited_once_with(devices)
                if action == "REFRESH":
                    finder.refresh_all_devices.assert_awaited_once()
                callback.answer.assert_awaited_once_with()

    async def test_device_selection_acknowledges_success(self):
        device = SimpleNamespace(name="dummy device")
        finder = SimpleNamespace(find_device_by_name=AsyncMock(return_value=device))
        video = SimpleNamespace(select_device=AsyncMock())
        callback = SimpleNamespace(answer=AsyncMock())

        await DeviceSelectButton("dummy device", video, finder).on_click(callback)

        video.select_device.assert_awaited_once_with(device)
        callback.answer.assert_awaited_once_with()

    async def test_download_retry_acknowledges_success(self):
        source_message = SimpleNamespace(text="https://media.invalid/video.mp4")
        reply_message = SimpleNamespace(reply_to_message=source_message)
        callback = SimpleNamespace(answer=AsyncMock(), message=reply_message)
        async def download(*_args):
            callback.answer.assert_awaited_once_with()

        downloader = SimpleNamespace(
            parse_link_message=Mock(return_value="https://media.invalid/video.mp4"),
            download_url=AsyncMock(side_effect=download),
        )

        await RetryDownloadButton("RETRY", downloader).on_click(callback)

        downloader.download_url.assert_awaited_once_with(
            source_message, "https://media.invalid/video.mp4", reply_message
        )
        callback.answer.assert_awaited_once_with()

    async def test_unavailable_device_and_invalid_retry_answer_only_with_error(self):
        finder = SimpleNamespace(find_device_by_name=AsyncMock(return_value=None))
        video = SimpleNamespace(select_device=AsyncMock())
        callback = SimpleNamespace(answer=AsyncMock())
        await DeviceSelectButton("missing device", video, finder).on_click(callback)
        callback.answer.assert_awaited_once_with("Wrong device")
        video.select_device.assert_not_awaited()

        callback = SimpleNamespace(answer=AsyncMock(), message=SimpleNamespace(reply_to_message=None))
        downloader = SimpleNamespace(parse_link_message=Mock(return_value=None), download_url=AsyncMock())
        await RetryDownloadButton("RETRY", downloader).on_click(callback)
        callback.answer.assert_awaited_once_with("Url no longer exists")
        downloader.download_url.assert_not_awaited()


if __name__ == "__main__":
    unittest.main(verbosity=2)
