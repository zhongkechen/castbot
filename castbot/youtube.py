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
_FORMAT = "best[protocol=https][ext=mp4][vcodec^=avc1][acodec^=mp4a]"
_UPSTREAM_HEADERS = {"accept", "accept-language", "origin", "referer", "user-agent"}
_REDIRECT_STATUSES = {301, 302, 303, 307, 308}


class YouTubeRelayError(Exception):
    pass


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


async def resolve_youtube_stream(video_id: str) -> YouTubeStream:
    url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        process = await asyncio.create_subprocess_exec(
            "yt-dlp", "--ignore-config", "--no-playlist", "--simulate",
            "--socket-timeout", "10", "--format", _FORMAT,
            "--print", "%(.{url,title,http_headers})j", "--", url,
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
