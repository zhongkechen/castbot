import asyncio
import logging
import os.path
import re
import typing
from urllib.parse import quote

from aiohttp import ClientError, web
from aiohttp.web_request import Request
from aiohttp.web_response import Response, StreamResponse
from pyrogram.raw.types import MessageMediaDocument, Document, DocumentAttributeFilename, Message

from .client import BotClient
from .utils import LocalToken
from .youtube import YouTubeRelayError, YouTubeStream

__all__ = ["Http"]

_RANGE_REGEX = re.compile(r"bytes=([0-9]*)-([0-9]*)", re.IGNORECASE)


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

    def cancel(self):
        if self._task is not None and self._task is not asyncio.current_task():
            self._task.cancel()


def parse_http_range(http_range: str) -> tuple[int | None, int | None]:
    matches = _RANGE_REGEX.fullmatch(http_range.strip())
    if matches is None or not any(matches.groups()):
        raise ValueError("Invalid byte range")
    first, last = matches.groups()
    return int(first) if first else None, int(last) if last else None


class Http:
    def __init__(self, config, bot_client: BotClient, extra_routes):
        self._listen_port = int(config["listen_port"])
        self._listen_host = str(config["listen_host"])
        self._request_gone_timeout = int(config.get("request_gone_timeout", 900))
        self._block_size = int(config.get("block_size", 1048576))
        self._extra_routes = list(extra_routes)

        self._tokens: typing.Dict[LocalToken, typing.Any] = {}
        self._youtube_streams: dict[LocalToken, YouTubeStream] = {}
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

        # Stream and Web API paths contain credentials and must stay out of access logs.
        runner = web.AppRunner(app, handle_signals=True, access_log=None)
        await runner.setup()
        try:
            site = web.TCPSite(runner, self._listen_host, self._listen_port)
            await site.start()
            logging.info("======== Running on %s ========\n(Press CTRL+C to quit)", site.name)

            while True:
                await asyncio.sleep(3600)
        finally:
            await runner.cleanup()

    def add_remote_token(self, playing_video, youtube_stream: YouTubeStream | None = None) -> str:
        local_token = playing_video.local_token
        uri = f"http://{self._listen_host}:{self._listen_port}/stream/{local_token.message_id}/{local_token.token}"
        if youtube_stream is not None:
            self.remove_remote_token(local_token)
            self._youtube_streams[local_token] = youtube_stream
            self._feed_timeout(local_token, None)
        self._tokens[local_token] = playing_video
        return uri

    def remove_remote_token(self, local_token: LocalToken):
        self._tokens.pop(local_token, None)
        self._youtube_streams.pop(local_token, None)
        self._downloaded_blocks.pop(local_token, None)
        debounce = self._stream_debounce.pop(local_token, None)
        if debounce is not None:
            debounce.cancel()
        for transport in self._stream_transports.pop(local_token, ()):
            transport.close()

    def has_remote_token(self, local_token: LocalToken) -> bool:
        return local_token in self._tokens

    def keep_youtube_stream(self, local_token: LocalToken):
        if local_token in self._youtube_streams:
            self._feed_timeout(local_token, None)

    @staticmethod
    def _write_http_range_headers(
        result: StreamResponse, start: int, stop: int, size: int, partial: bool
    ):
        if partial:
            result.headers["Content-Range"] = f"bytes {start}-{stop - 1}/{size}"
        result.headers["Accept-Ranges"] = "bytes"
        result.headers["Content-Length"] = str(stop - start)

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

    def _feed_timeout(self, local_token: LocalToken, size: int | None):
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

    async def _timeout_handler(self, local_token: LocalToken, size: int | None):
        if any(not transport.is_closing() for transport in self._get_stream_transports(local_token)):
            self._stream_debounce[local_token].reschedule()
            return

        remaining = None
        if size is not None:
            blocks = (size + self._block_size - 1) // self._block_size
            downloaded = len(self._downloaded_blocks.get(local_token, ()))
            remaining = max(0, blocks - downloaded) / blocks * 100 if blocks else 0
        playing_video = self._tokens.get(local_token)
        self.remove_remote_token(local_token)
        if playing_video is not None:
            await playing_video.close(remaining)

    async def _relay_youtube(self, request: Request, local_token: LocalToken, source: YouTubeStream) -> StreamResponse:
        byte_range = request.headers.get("Range") if request.method == "GET" else None
        if byte_range is not None:
            try:
                parse_http_range(byte_range)
            except ValueError:
                return Response(status=400)

        self._feed_timeout(local_token, None)
        stream = None
        active = None
        transport = request.transport
        try:
            async with source.open(request.method, byte_range) as upstream:
                if self._youtube_streams.get(local_token) is not source:
                    return Response(status=403)
                if upstream.status == 416:
                    headers = {}
                    if "Content-Range" in upstream.headers:
                        headers["Content-Range"] = upstream.headers["Content-Range"]
                    return Response(status=416, headers=headers)
                encoding = upstream.headers.get("Content-Encoding", "identity")
                if upstream.status not in (200, 206) or encoding != "identity":
                    logging.warning("YouTube media request returned HTTP %s", upstream.status)
                    return Response(status=502)

                headers = {
                    name: upstream.headers[name]
                    for name in ("Content-Length", "Content-Range", "Accept-Ranges")
                    if name in upstream.headers
                }
                if request.method == "HEAD":
                    response = Response(status=upstream.status, headers=headers)
                    self._write_access_control_headers(response)
                    return response

                stream = StreamResponse(status=upstream.status, headers=headers)
                self._write_access_control_headers(stream)
                if transport is not None:
                    active = self._stream_transports.setdefault(local_token, set())
                    active.add(transport)
                stream.force_close()
                await stream.prepare(request)
                async for chunk in upstream.content.iter_chunked(64 * 1024):
                    await stream.write(chunk)
                await stream.write_eof()
                return stream
        except (YouTubeRelayError, ClientError, OSError, TimeoutError, ValueError) as error:
            logging.warning("YouTube media relay interrupted (%s)", type(error).__name__)
            if stream is None:
                return Response(status=502)
            if transport is not None:
                transport.close()
            return stream
        finally:
            if active is not None:
                active.discard(transport)

    async def _stream_handler(self, request: Request) -> Response | StreamResponse:
        message_id = request.match_info["message_id"]
        token = request.match_info["token"]
        if not all(value.isascii() and value.isdecimal() for value in (message_id, token)):
            return Response(status=401)

        try:
            local_token = LocalToken(message_id, token)
        except ValueError:
            return Response(status=401)

        if local_token.token >= 1 << 64:
            return Response(status=403)

        if not self.has_remote_token(local_token):
            return Response(status=403)

        youtube_stream = self._youtube_streams.get(local_token)
        if youtube_stream is not None:
            return await self._relay_youtube(request, local_token, youtube_stream)

        try:
            message = await self._bot_client.get_message(local_token.message_id)
        except ValueError:
            return Response(status=404)

        if not isinstance(message.media, MessageMediaDocument):
            return Response(status=404)

        if not isinstance(message.media.document, Document):
            return Response(status=404)

        size = message.media.document.size
        start, stop = 0, size
        range_header = request.headers.get("Range") if request.method == "GET" else None
        if range_header is not None:
            try:
                first, last = parse_http_range(range_header)
            except ValueError:
                return Response(status=400)
            if first is None:
                assert last is not None  # The parser requires at least one bound.
                start = max(size - last, 0)
            else:
                start = first
                if last is not None:
                    stop = min(last + 1, size)
            if start >= stop:
                return Response(status=416, headers={"Content-Range": f"bytes */{size}"})

        partial = range_header is not None
        status_code = 206 if partial else 200
        offset = (start // self._block_size) * self._block_size

        try:
            filename = mtproto_filename(message)
        except TypeError:
            filename = f"file_{message.media.document.id}"

        logging.info("Incoming streaming request: %s message %s", request.method, local_token.message_id)

        if request.method == "HEAD":
            response = Response(status=status_code)
            self._write_http_range_headers(response, start, stop, size, partial)
            self._write_filename_header(response, filename)
            self._write_access_control_headers(response)
            return response

        stream = StreamResponse(status=status_code)
        self._write_http_range_headers(stream, start, stop, size, partial)
        self._write_filename_header(stream, filename)
        self._write_access_control_headers(stream)

        # Advertise the close before sending headers so the client opens a new connection for its next range.
        stream.force_close()
        await stream.prepare(request)

        try:
            while offset < stop:
                self._feed_timeout(local_token, size)
                block = await self._bot_client.get_block(message, offset, self._block_size)
                if not block:
                    break
                new_offset = offset + len(block)
                block = block[max(start - offset, 0):stop - offset]

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
            logging.warning("Broken streaming connection for message %s", local_token.message_id)
        return stream
