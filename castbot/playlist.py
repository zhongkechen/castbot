import asyncio
import logging
from contextlib import aclosing

from .device import Device, PlaybackStatus
from .http import Http
from .utils import DeviceControlError, LocalToken
from .youtube import YouTubeRelayError, YouTubeStream, iter_youtube_playlist, resolve_youtube_stream


_POLL_INTERVAL = 1


class PlaylistTrack:
    def __init__(self, message_id: int):
        self.local_token = LocalToken(message_id)
        self.url = ""
        self.expired = False

    async def close(self, _remaining):
        self.expired = True


class PlaylistPlayback:
    def __init__(self, playlist_id: str, message_id: int, device: Device, http: Http, on_item, on_finish):
        self._playlist_id = playlist_id
        self._message_id = message_id
        self._device = device
        self._http = http
        self._on_item = on_item
        self._on_finish = on_finish
        self._started = asyncio.get_running_loop().create_future()
        self._task: asyncio.Task | None = None
        self._stop_requested = False

    async def start(self):
        self._task = asyncio.create_task(self._run())
        try:
            await self._started
        except asyncio.CancelledError:
            await self.stop()
            raise

    async def stop(self):
        if not self._started.done():
            self._started.set_exception(YouTubeRelayError("Playlist playback was interrupted."))
        if self._task is not None and not self._task.done():
            if not self._stop_requested:
                self._stop_requested = True
                self._task.cancel()
            await asyncio.shield(asyncio.gather(self._task, return_exceptions=True))

    async def _run(self):
        started = False
        notice = None
        skipped = 0
        try:
            async with aclosing(iter_youtube_playlist(self._playlist_id)) as entries:
                index = 0
                async for video_id in entries:
                    index += 1
                    try:
                        source = await resolve_youtube_stream(video_id)
                    except YouTubeRelayError:
                        logging.info("Skipping unavailable YouTube playlist item %s", video_id)
                        skipped += 1
                        continue
                    if not started:
                        await self._device.stop()
                    track = PlaylistTrack(self._message_id)
                    try:
                        await self._play_item(track, source, index)
                        if not started:
                            started = True
                            if not self._started.done():
                                self._started.set_result(None)
                        await self._wait_for_end(track)
                    finally:
                        self._http.remove_remote_token(track.local_token)
                        await self._device.close_playlist_item(track.local_token)
            if not started:
                raise YouTubeRelayError("This playlist has no playable YouTube MP4 videos.")
            notice = "Playlist finished."
            if skipped:
                notice = f"Playlist finished. Skipped {skipped} unavailable video(s)."
        except Exception as error:
            if not self._started.done():
                self._started.set_exception(error)
            else:
                logging.warning("YouTube playlist stopped (%s)", type(error).__name__)
                notice = "Playlist could not continue."
                if isinstance(error, (YouTubeRelayError, DeviceControlError)):
                    notice = str(error)
        finally:
            try:
                await self._on_finish(started, notice)
            except Exception as error:
                logging.warning("Could not update YouTube playlist controls (%s)", type(error).__name__)

    async def _play_item(self, track: PlaylistTrack, source: YouTubeStream, index: int):
        track.url = self._http.add_remote_token(track, source)
        await self._device.play_playlist_item(track.url, source.title, track.local_token)
        await self._on_item(index)

    async def _wait_for_end(self, track: PlaylistTrack):
        loop = asyncio.get_running_loop()
        start_deadline = loop.time() + 45
        active = False
        while not track.expired:
            async with asyncio.timeout(10):
                status = await self._device.playlist_status(track.url)
            if status == PlaybackStatus.FINISHED or (active and status == PlaybackStatus.IDLE):
                return
            if status == PlaybackStatus.INTERRUPTED:
                raise DeviceControlError("Playlist playback was interrupted.")
            if status == PlaybackStatus.ACTIVE:
                active = True
                self._http.keep_youtube_stream(track.local_token)
            elif not active and loop.time() >= start_deadline:
                raise DeviceControlError("The device did not start the playlist video.")
            await asyncio.sleep(_POLL_INTERVAL)
        raise DeviceControlError("The device stopped requesting the playlist video.")
