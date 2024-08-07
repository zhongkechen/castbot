import asyncio
import logging
import os.path
import re
import typing
from urllib.parse import quote

from aiohttp import web
from aiohttp.web_request import Request
from aiohttp.web_response import Response, StreamResponse
from pyrogram.raw.types import MessageMediaDocument, Document, DocumentAttributeFilename, Message

from .client import BotClient
from .utils import LocalToken

__all__ = ["Http"]

_RANGE_REGEX = re.compile(r"bytes=([0-9]+)-([0-9]+)?")


def mtproto_filename(message: Message) -> str:
    if not (isinstance(message.media, MessageMediaDocument) and isinstance(message.media.document, Document)):
        raise TypeError()

    try:
        return next(
            attr.file_name for attr in message.media.document.attributes if isinstance(attr, DocumentAttributeFilename)
        )
    except StopIteration as error:
        raise TypeError() from error


async def _debounce_wrap(
    function: typing.Callable[..., typing.Coroutine], args: typing.Tuple[typing.Any, ...], timeout: int
):
    await asyncio.sleep(timeout)
    await function(*args)


class AsyncDebounce:
    def __init__(self, function: typing.Callable[..., typing.Coroutine], timeout: int):
        self._function = function
        self._timeout = timeout
        self._task: typing.Optional[asyncio.Task] = None
        self._args: typing.Optional[typing.Tuple[typing.Any, ...]] = None

    def _run(self) -> bool:
        if self._args is None:
            return False

        self._task = asyncio.get_event_loop().create_task(_debounce_wrap(self._function, self._args, self._timeout))
        return True

    def update_args(self, *args) -> bool:
        if self._task is not None and self._task.done():
            return False

        if self._task is not None:
            self._task.cancel()

        self._args = args
        return self._run()

    def reschedule(self):
        return self._run()


def parse_http_range(http_range: str, block_size: int) -> typing.Tuple[int, int, typing.Optional[int]]:
    matches = _RANGE_REGEX.search(http_range)

    if matches is None:
        raise ValueError()

    offset = matches.group(1)

    if not offset.isdigit():
        raise ValueError()

    max_size = matches.group(2)

    if max_size and max_size.isdigit():
        max_size = int(max_size)
    else:
        max_size = None

    offset = int(offset)
    safe_offset = (offset // block_size) * block_size
    data_to_skip = offset - safe_offset

    return safe_offset, data_to_skip, max_size


class Http:
    def __init__(self, config, bot_client: BotClient, extra_routes):
        self._listen_port = int(config["listen_port"])
        self._listen_host = str(config["listen_host"])
        self._request_gone_timeout = int(config.get("request_gone_timeout", 900))
        self._block_size = int(config.get("block_size", 1048576))
        self._extra_routes = list(extra_routes)

        self._tokens: typing.Dict[LocalToken, typing.Any] = {}
        self._downloaded_blocks: typing.Dict[LocalToken, typing.Set[int]] = {}
        self._stream_debounce: typing.Dict[LocalToken, AsyncDebounce] = {}
        self._stream_transports: typing.Dict[LocalToken, typing.Set[asyncio.Transport]] = {}
        self._bot_client = bot_client

    async def start(self):
        app = web.Application()
        app.router.add_static("/static/", os.path.dirname(__file__) + "/static/")
        app.router.add_get("/stream/{message_id}/{token}", self._stream_handler)
        app.router.add_options("/stream/{message_id}/{token}", self._upnp_discovery_handler)
        app.router.add_put("/stream/{message_id}/{token}", self._upnp_discovery_handler)
        app.router.add_get("/healthcheck", self._health_check_handler)

        for method, path, handle in self._extra_routes:
            logging.info("extra route: %s %s", method, path)
            app.router.add_route(method, path, handle)

        runner = web.AppRunner(app, handle_signals=True)
        await runner.setup()
        try:
            site = web.TCPSite(runner, self._listen_host, self._listen_port)
            await site.start()
            logging.info("======== Running on %s ========\n(Press CTRL+C to quit)", site.name)

            while True:
                await asyncio.sleep(3600)
        finally:
            await runner.cleanup()

    def add_remote_token(self, playing_video) -> str:
        local_token = playing_video.local_token
        uri = f"http://{self._listen_host}:{self._listen_port}/stream/{local_token.message_id}/{local_token.token}"
        self._tokens[local_token] = playing_video
        return uri

    def _check_local_token(self, local_token: LocalToken) -> bool:
        return local_token in self._tokens

    @staticmethod
    def _write_http_range_headers(result: StreamResponse, read_after: int, size: int, max_size: int):
        result.headers.setdefault("Content-Range", f"bytes {read_after}-{max_size}/{size}")
        result.headers.setdefault("Accept-Ranges", "bytes")
        result.headers.setdefault("Content-Length", str(size))

    @staticmethod
    def _write_access_control_headers(result: StreamResponse):
        result.headers.setdefault("Content-Type", "video/mp4")
        result.headers.setdefault("Access-Control-Allow-Origin", "*")
        result.headers.setdefault("Access-Control-Allow-Methods", "GET, OPTIONS")
        result.headers.setdefault("Access-Control-Allow-Headers", "Content-Type")
        result.headers.setdefault("transferMode.dlna.org", "Streaming")
        result.headers.setdefault("TimeSeekRange.dlna.org", "npt=0.00-")

        # This line is causing Samsung TV to fail
        # result.headers.setdefault("contentFeatures.dlna.org", "DLNA.ORG_OP=01;DLNA.ORG_CI=0;")

    @staticmethod
    def _write_filename_header(result: StreamResponse, filename: str):
        result.headers.setdefault("Content-Disposition", f'inline; filename="{quote(filename)}"')

    async def _health_check_handler(self, _: Request) -> typing.Optional[Response]:
        try:
            await self._bot_client.health_check()
            return Response(text="ok")
        except ConnectionError:
            return Response(status=500, text="gone")

    async def _upnp_discovery_handler(self, _: Request) -> typing.Optional[Response]:
        result = Response()
        self._write_access_control_headers(result)
        return result

    def _feed_timeout(self, local_token: LocalToken, size: int):
        debounce = self._stream_debounce.setdefault(
            local_token,
            AsyncDebounce(self._timeout_handler, self._request_gone_timeout),
        )

        debounce.update_args(local_token, size)

    def _feed_downloaded_blocks(self, block_id: int, local_token: LocalToken):
        downloaded_blocks = self._downloaded_blocks.setdefault(local_token, set())
        downloaded_blocks.add(block_id)

    def _feed_stream_transport(self, local_token: LocalToken, transport: asyncio.Transport):
        transports = self._stream_transports.setdefault(local_token, set())
        transports.add(transport)

    def _get_stream_transports(self, local_token: LocalToken) -> typing.Set[asyncio.Transport]:
        return self._stream_transports[local_token] if local_token in self._stream_transports else set()

    async def _timeout_handler(self, local_token: LocalToken, size: int):
        _debounce: typing.Optional[AsyncDebounce] = None  # avoid garbage collector

        if all(t.is_closing() for t in self._get_stream_transports(local_token)):
            blocks = (size // self._block_size) + 1

            if local_token in self._downloaded_blocks:
                remain_blocks = blocks - len(self._downloaded_blocks[local_token])
                del self._downloaded_blocks[local_token]
            else:
                remain_blocks = blocks

            if local_token in self._tokens:
                remain_blocks_perceptual = remain_blocks / blocks * 100
                await self._tokens[local_token].close(remain_blocks_perceptual)
                del self._tokens[local_token]

            if local_token in self._stream_debounce:
                _debounce = self._stream_debounce[local_token]
                del self._stream_debounce[local_token]

            if local_token in self._stream_transports:
                del self._stream_transports[local_token]

        if local_token in self._stream_debounce:
            self._stream_debounce[local_token].reschedule()

        del _debounce

    async def _stream_handler(self, request: Request) -> typing.Optional[Response]:
        _message_id: str = request.match_info["message_id"]

        if not _message_id.isdigit():
            return Response(status=401)

        _token: str = request.match_info["token"]

        if not _token.isdigit():
            return Response(status=401)

        local_token = LocalToken(_message_id, _token)
        del _token
        del _message_id

        if not self._check_local_token(local_token):
            return Response(status=403)

        range_header = request.headers.get("Range")

        if range_header is None:
            offset = 0
            data_to_skip = 0
            max_size = None
        else:
            try:
                offset, data_to_skip, max_size = parse_http_range(range_header, self._block_size)
            except ValueError:
                return Response(status=400)

        if data_to_skip > self._block_size:
            return Response(status=500)

        try:
            message = await self._bot_client.get_message(local_token.message_id)
        except ValueError:
            return Response(status=404)

        if not isinstance(message.media, MessageMediaDocument):
            return Response(status=404)

        if not isinstance(message.media.document, Document):
            return Response(status=404)

        size = message.media.document.size
        read_after = offset + data_to_skip

        if read_after > size:
            return Response(status=400)

        if (max_size is not None) and (size < max_size):
            return Response(status=400)

        if max_size is None:
            max_size = size

        status_code = 206 if (read_after or (max_size != size)) else 200

        try:
            filename = mtproto_filename(message)
        except TypeError:
            filename = f"file_{message.media.document.id}"

        logging.info("Incoming streaming request: %s %s %s", request.method, local_token, request.headers)

        if request.method == "HEAD":
            response = Response(status=status_code)
            self._write_http_range_headers(response, read_after, size, max_size)
            self._write_filename_header(response, filename)
            self._write_access_control_headers(response)
            return response

        stream = StreamResponse(status=status_code)
        self._write_http_range_headers(stream, read_after, size, max_size)
        self._write_filename_header(stream, filename)
        self._write_access_control_headers(stream)

        await stream.prepare(request)

        try:
            while offset < max_size:
                self._feed_timeout(local_token, size)
                block = await self._bot_client.get_block(message, offset, self._block_size)
                new_offset = offset + len(block)

                if data_to_skip:
                    block = block[data_to_skip:]
                    data_to_skip = False

                if new_offset > max_size:
                    block = block[: -(new_offset - max_size)]

                if request.transport is None:
                    break

                self._feed_stream_transport(local_token, request.transport)

                if request.transport.is_closing():
                    break

                await stream.write(block)
                self._feed_downloaded_blocks(offset, local_token)
                offset = new_offset

            await stream.write_eof()
        except (ConnectionResetError, BrokenPipeError, ConnectionError):
            logging.warning("Broken streaming connection: %s %s", local_token, request.headers)
