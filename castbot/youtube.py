import asyncio
import json
import re
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlsplit

from aiohttp import ClientSession, ClientTimeout
from yarl import URL


_YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}
_VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}")
_PLAYLIST_ID = re.compile(r"[A-Za-z0-9_-]+")
_FORMAT_FILTER = "[protocol=https][ext=mp4][vcodec^=avc1][acodec^=mp4a]"
_FORMAT_ID = re.compile(r"[A-Za-z0-9_-]{1,20}")
_UPSTREAM_HEADERS = {"accept", "accept-language", "origin", "referer", "user-agent"}
_REDIRECT_STATUSES = {301, 302, 303, 307, 308}


class YouTubeRelayError(Exception):
    pass


@dataclass(frozen=True)
class StreamOption:
    value: str
    label: str


AUTO_STREAM = StreamOption("", "Auto")
PLAYLIST_STREAM_OPTIONS = tuple(StreamOption(str(height), f"Up to {height}p") for height in (360, 480, 720, 1080))


def youtube_video_id(url: str) -> str | None:
    try:
        parsed = urlsplit(url)
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"}:
        return None
    if parsed.hostname == "youtu.be":
        video_id = parsed.path.strip("/")
    elif parsed.hostname in _YOUTUBE_HOSTS:
        if parsed.path == "/watch":
            video_id = parse_qs(parsed.query).get("v", [""])[0]
        else:
            path = parsed.path.strip("/").split("/")
            video_id = path[1] if len(path) == 2 and path[0] in {"shorts", "live", "embed"} else ""
    else:
        return None
    return video_id if _VIDEO_ID.fullmatch(video_id) else None


def youtube_playlist_id(url: str) -> str | None:
    try:
        parsed = urlsplit(url)
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in _YOUTUBE_HOSTS or parsed.path != "/playlist":
        return None
    playlist_id = parse_qs(parsed.query).get("list", [""])[0]
    return playlist_id if _PLAYLIST_ID.fullmatch(playlist_id) else None


async def iter_youtube_playlist(playlist_id: str):
    url = f"https://www.youtube.com/playlist?list={playlist_id}"
    try:
        process = await asyncio.create_subprocess_exec(
            "yt-dlp", "--ignore-config", "--yes-playlist", "--flat-playlist", "--lazy-playlist",
            "--simulate", "--socket-timeout", "10", "--print", "%(id)s", "--", url,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            while line := await asyncio.wait_for(process.stdout.readline(), timeout=30):
                video_id = line.decode("ascii", errors="replace").strip()
                if _VIDEO_ID.fullmatch(video_id):
                    yield video_id
            if await asyncio.wait_for(process.wait(), timeout=5) != 0:
                raise YouTubeRelayError("Could not read this YouTube playlist.")
        finally:
            if process.returncode is None:
                with suppress(ProcessLookupError):
                    process.kill()
                await process.communicate()
    except (OSError, TimeoutError, ValueError):
        raise YouTubeRelayError("Could not read this YouTube playlist.") from None


def _is_youtube_media_url(url: URL) -> bool:
    return (
        url.scheme == "https"
        and (url.host or "").endswith(".googlevideo.com")
        and url.port == 443
        and url.user is None
        and url.password is None
    )


@dataclass(frozen=True)
class YouTubeStream:
    url: URL = field(repr=False)
    title: str
    headers: dict[str, str] = field(repr=False)

    @asynccontextmanager
    async def open(self, method: str, byte_range: str | None):
        headers = {**self.headers, "Accept-Encoding": "identity"}
        if byte_range is not None:
            headers["Range"] = byte_range

        url = self.url
        timeout = ClientTimeout(total=None, connect=15, sock_read=30)
        async with ClientSession(timeout=timeout, auto_decompress=False, trust_env=True) as session:
            for _ in range(4):
                async with session.request(method, url, headers=headers, allow_redirects=False) as response:
                    if response.status not in _REDIRECT_STATUSES:
                        yield response
                        return
                    destination = response.headers.get("Location")
                    if not destination:
                        break
                    url = url.join(URL(destination, encoded=True))
                    if not _is_youtube_media_url(url):
                        break
        raise YouTubeRelayError("YouTube redirected to an unsupported media address.")


async def _youtube_metadata(video_id: str, selector: str, fields: str) -> bytes:
    url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        process = await asyncio.create_subprocess_exec(
            "yt-dlp", "--ignore-config", "--no-playlist", "--simulate",
            "--socket-timeout", "10", "--format", selector,
            "--print", fields, "--", url,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=30)
        except (TimeoutError, asyncio.CancelledError):
            if process.returncode is None:
                with suppress(ProcessLookupError):
                    process.kill()
                await process.communicate()
            raise
        if process.returncode != 0:
            raise YouTubeRelayError("Could not resolve a playable YouTube MP4 for this video.")
        return stdout
    except (OSError, TimeoutError):
        raise YouTubeRelayError("Could not resolve a playable YouTube MP4 for this video.") from None


async def list_youtube_streams(video_id: str) -> list[StreamOption]:
    stdout = await _youtube_metadata(video_id, f"all{_FORMAT_FILTER}", "%(.{format_id,height,fps,url})j")
    options = {}
    for line in stdout.splitlines():
        try:
            info = json.loads(line)
            format_id = info["format_id"]
            if not _FORMAT_ID.fullmatch(format_id) or not _is_youtube_media_url(URL(info["url"], encoded=True)):
                continue
            height, fps = info.get("height"), info.get("fps")
            parts = [f"{height}p"] if isinstance(height, int) and height > 0 else []
            if isinstance(fps, (int, float)) and fps > 0:
                parts.append(f"{fps:g} fps")
            parts.append(f"MP4 (#{format_id})")
            options[format_id] = StreamOption(format_id, " · ".join(parts))
        except (KeyError, ValueError, TypeError):
            continue
    if not options:
        raise YouTubeRelayError("No compatible YouTube streams were found.")
    return list(options.values())


async def resolve_youtube_stream(video_id: str, *, format_id: str | None = None,
                                 max_height: int | None = None) -> YouTubeStream:
    selector = f"best{_FORMAT_FILTER}"
    if format_id:
        if not _FORMAT_ID.fullmatch(format_id):
            raise YouTubeRelayError("This YouTube stream is unavailable. Use STREAM to pick another.")
        # yt-dlp treats unquoted numeric filter values as numbers, but format IDs are strings.
        selector += f"[format_id='{format_id}']"
    if max_height is not None:
        selector += f"[height<={max_height}]"
    try:
        stdout = await _youtube_metadata(video_id, selector, "%(.{url,title,http_headers})j")
    except YouTubeRelayError:
        if format_id:
            raise YouTubeRelayError("This YouTube stream is unavailable. Use STREAM to pick another.") from None
        raise
    try:
        info = json.loads(stdout)
        media_url = URL(info["url"], encoded=True)
        if not _is_youtube_media_url(media_url):
            raise YouTubeRelayError("YouTube returned an unsupported media address.")
        headers = {
            name: value for name, value in info["http_headers"].items() if name.lower() in _UPSTREAM_HEADERS
        }
        return YouTubeStream(media_url, info.get("title") or video_id, headers)
    except (OSError, TimeoutError, AttributeError, ValueError, KeyError, TypeError):
        raise YouTubeRelayError("Could not resolve a playable YouTube MP4 for this video.") from None
