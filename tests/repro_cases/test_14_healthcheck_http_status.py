"""Verify response statuses are reflected in the health-check exit code."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import castbot.__main__ as main_module
from castbot.http import Http


class ResponseContext:
    def __init__(self, response):
        self.response = response

    async def __aenter__(self):
        return self.response

    async def __aexit__(self, *_args):
        return False


class RecordedSession:
    def __init__(self, response):
        self.response = response
        self.urls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    def get(self, url, *, allow_redirects):
        self.urls.append((url, allow_redirects))
        return ResponseContext(self.response)


class HealthStatusTest(unittest.IsolatedAsyncioTestCase):
    async def check_status(self, bot_health_check):
        config = {"http": {"listen_host": "127.0.0.1", "listen_port": 8350}}
        server = Http(config["http"], SimpleNamespace(health_check=bot_health_check), [])
        response = await server._health_check_handler(None)
        session = RecordedSession(response)
        with patch.object(main_module.aiohttp, "ClientSession", return_value=session):
            exit_code = await main_module.health_check(config)
        self.assertEqual(session.urls, [("http://127.0.0.1:8350/healthcheck", False)])
        bot_health_check.assert_awaited_once()
        return response, exit_code

    async def test_disconnected_bot_exits_unhealthy(self):
        response, exit_code = await self.check_status(AsyncMock(side_effect=ConnectionError("dummy disconnect")))
        self.assertEqual(response.status, 500)
        self.assertEqual(exit_code, 1)

    async def test_healthy_bot_control_returns_http_200_and_success(self):
        response, exit_code = await self.check_status(AsyncMock())
        self.assertEqual(response.status, 200)
        self.assertEqual(exit_code, 0)


    async def test_health_check_rejects_redirects_and_handles_connection_failures(self):
        config = {"http": {"listen_host": "127.0.0.1", "listen_port": 8350}}
        session = RecordedSession(SimpleNamespace(status=302))
        with patch.object(main_module.aiohttp, "ClientSession", return_value=session):
            self.assertEqual(await main_module.health_check(config), 1)
        with patch.object(main_module.aiohttp, "ClientSession", side_effect=ConnectionError):
            with self.assertLogs(level="ERROR"):
                self.assertEqual(await main_module.health_check(config), 1)


if __name__ == "__main__":
    unittest.main()
