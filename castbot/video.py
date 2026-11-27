import asyncio
import html
import logging
import re
import typing

from pyrogram import Client
from pyrogram.errors import MessageNotModified
from pyrogram.raw.types import MessageMediaDocument
from pyrogram.types import Message, InlineKeyboardMarkup

from .button import DeviceSelectButton, PlayButton, StopButton, PauseButton, ResumeButton, RefreshButton, DeviceButton
from .button import StreamButton
from .client import BotClient
from .device import Device, DeviceFinderCollection
from .downloader import extract_url
from .playlist import PlaylistPlayback
from .utils import LocalToken, NoDeviceException, ActionNotSupportedException
from .http import Http
from .youtube import AUTO_STREAM, PLAYLIST_STREAM_OPTIONS, StreamOption, YouTubeRelayError, YouTubeStream
from .youtube import list_youtube_streams, resolve_youtube_stream, youtube_playlist_id, youtube_video_id


_STREAM_LINE = "\nStream: "


class UserData:
    selected_device: typing.Optional[Device] = None

    def __init__(self, selected_device):
        self.selected_device = selected_device


class PlayingVideos:
    def __init__(self, http: Http, device_finders: DeviceFinderCollection, bot_client: BotClient):
        self._http = http
        self._device_finders = device_finders
        self._bot_client = bot_client
        self._playing_videos: typing.Dict[LocalToken, PlayingVideo] = {}
        self._user_data: typing.Dict[int, UserData] = {}
        self._playlists: dict[str, tuple[PlayingVideo, PlaylistPlayback]] = {}

    async def on_new_video(self, _: Client | None, video_message: Message, link_message=None):
        user_id = (link_message or video_message).from_user.id
        local_token = LocalToken(video_message.id)

        video = self.new_video(local_token, user_id, video_message,
                               link_message=link_message,
                               control_message=None)
        await video.send_stopped_control_message()

    async def on_new_youtube(self, message: Message, video_id: str | None, control_message=None, *, playlist_id=None):
        video = self.new_video(
            LocalToken(message.id), message.from_user.id, message, control_message=control_message,
            youtube_id=video_id, playlist_id=playlist_id,
        )
        await video.send_stopped_control_message()

    def remove(self, playing_video: "PlayingVideo"):
        local_token = playing_video.local_token
        if local_token in self._playing_videos:
            del self._playing_videos[local_token]

    def new_video(self, local_token: LocalToken, user_id, video_message,
                  link_message=None, control_message=None, device=None, youtube_id=None, playlist_id=None):
        device = device or self.get_user_device(user_id)
        self._playing_videos[local_token] = PlayingVideo(
            local_token=local_token,
            user_id=user_id,
            playing_videos=self,
            playing_device=device,
            video_message=video_message,
            link_message=link_message,
            control_message=control_message,
            youtube_id=youtube_id,
            playlist_id=playlist_id,
        )
        return self._playing_videos[local_token]

    def add_to_http(self, playing_video, youtube_stream: YouTubeStream | None = None, *, relay=None):
        self._playing_videos[playing_video.local_token] = playing_video
        return self._http.add_remote_token(relay or playing_video, youtube_stream)

    def is_streaming(self, local_token: LocalToken):
        return self._http.has_remote_token(local_token)

    def remove_from_http(self, local_token: LocalToken):
        self._http.remove_remote_token(local_token)

    def has_active_playlist(self, device: Device) -> bool:
        return bool(self._playlists) and device.get_device_id() in self._playlists

    def is_playing(self, video: "PlayingVideo") -> bool:
        if video.playlist_id and video.playing_device:
            current = self._playlists.get(video.playing_device.get_device_id())
            return current is not None and current[0] is video
        return self.is_streaming(video.playback_token)

    async def interrupt_playlist(self, device: Device, owner=None) -> bool:
        if not self._playlists:
            return False
        device_id = device.get_device_id()
        interrupted = False
        while entry := self._playlists.get(device_id):
            video, playlist = entry
            if owner is not None and video is not owner:
                break
            await playlist.stop()
            if self._playlists.get(device_id) is entry:
                del self._playlists[device_id]
            interrupted = True
        return interrupted

    async def play_playlist(self, video: "PlayingVideo", device: Device, playlist_id: str, max_height: int | None):
        await self.interrupt_playlist(device)
        device_id = device.get_device_id()

        async def finished(started, notice):
            try:
                if started:
                    await video.finish_playlist(notice)
            finally:
                if self._playlists.get(device_id) is entry:
                    del self._playlists[device_id]

        entry = (
            video,
            PlaylistPlayback(playlist_id, video.local_token.message_id, device, self._http,
                             video.show_playlist_item, finished, max_height=max_height),
        )
        self._playlists[device_id] = entry
        await entry[1].start()

    async def reconstruct_playing_video(self, local_token: LocalToken, user_id, control_message,
                                        *, device_id=None):
        if local_token in self._playing_videos:
            return self._playing_videos[local_token]
        # re-construct PlayVideo when the bot is restarted
        video_message: Message = await self._bot_client.get_message(local_token.message_id)
        youtube_id = None
        playlist_id = None
        if not isinstance(getattr(video_message, "media", None), MessageMediaDocument):
            link = extract_url(getattr(video_message, "message", None))
            if link:
                youtube_id = youtube_video_id(link)
                playlist_id = youtube_playlist_id(link)
        if control_message.reply_to_message_id and control_message.reply_to_message_id != local_token.message_id:
            link_message = await self._bot_client.get_message(control_message.reply_to_message_id)
        else:
            link_message = None

        if device_id:
            device = await self._device_finders.find_device_by_id(device_id)
        else:
            device_name = PlayingVideo.parse_device_str(control_message.text)
            device = await self._device_finders.find_device_by_name(device_name) if device_name else None
            device = device or self.get_user_device(user_id)

        video = self.new_video(local_token, user_id, video_message,
                               link_message=link_message, control_message=control_message,
                               youtube_id=youtube_id, playlist_id=playlist_id)
        video.playing_device = device
        video.restore_stream_choice(getattr(control_message, "text", None))
        return video

    async def handle_closed(self, remains: float, local_token: LocalToken):
        if local_token in self._playing_videos:
            playing_video = self._playing_videos[local_token]
            device = playing_video.playing_device
            await playing_video.send_stopped_control_message(remaining=remains)
            del self._playing_videos[local_token]
            await device.on_close(local_token)

    def get_user_device(self, user_id):
        user_data = self._user_data.get(user_id)
        if not user_data or not user_data.selected_device:
            return None

        return user_data.selected_device

    def set_user_device(self, user_id, device):
        user_data = self._user_data.get(user_id) or UserData(device)
        user_data.selected_device = device
        self._user_data[user_id] = user_data


class YouTubePlayback:
    def __init__(self, video: "PlayingVideo"):
        self.local_token = LocalToken(video.local_token.message_id)
        self._video = video

    async def close(self, remaining):
        await self._video.close(remaining, relay=self)


class PlayingVideo:
    def __init__(
        self,
        local_token: LocalToken,
        user_id: int,
        playing_videos: PlayingVideos,
        playing_device: typing.Optional[Device] = None,
        video_message: typing.Optional[Message] = None,
        link_message: typing.Optional[Message] = None,
        control_message: typing.Optional[Message] = None,
        youtube_id: str | None = None,
        playlist_id: str | None = None,
    ):
        self.local_token = local_token
        self.user_id = user_id
        self.video_message = video_message
        self.playing_device: typing.Optional[Device] = playing_device
        self.link_message = link_message
        self.control_message = control_message
        self.playing_videos = playing_videos
        self.youtube_id = youtube_id
        self.playlist_id = playlist_id
        self._playlist_index = None
        self._playback_lock = asyncio.Lock()
        self._stream_choice = AUTO_STREAM
        self._stream_options: list[StreamOption] | None = None
        self._youtube_playback: YouTubePlayback | None = None

    @property
    def playback_token(self) -> LocalToken:
        if self._youtube_playback is not None:
            return self._youtube_playback.local_token
        return self.local_token

    @property
    def is_youtube(self) -> bool:
        return bool(self.youtube_id or self.playlist_id)

    def restore_stream_choice(self, text: str | None):
        _, _, label = (text or "").rpartition(_STREAM_LINE)
        if self.playlist_id:
            self._stream_choice = next((option for option in PLAYLIST_STREAM_OPTIONS if option.label == label),
                                       AUTO_STREAM)
        elif self.youtube_id:
            format_id = re.search(r"\(#([A-Za-z0-9_-]{1,20})\)$", label)
            if format_id:
                self._stream_choice = StreamOption(format_id[1], label)

    async def _get_stream_options(self):
        if self.playlist_id:
            return [AUTO_STREAM, *PLAYLIST_STREAM_OPTIONS]
        if self._stream_options is None:
            self._stream_options = await list_youtube_streams(self.youtube_id)
        return [AUTO_STREAM, *self._stream_options]

    async def _show_stream_menu(self):
        self._stream_options = None
        options = await self._get_stream_options()
        buttons = [
            [StreamButton(self, "✓ " + option.label if option.value == self._stream_choice.value else option.label,
                          action="pick" + option.value).get_button()]
            for option in options
        ]
        buttons.append([StreamButton(self, "BACK", action="back").get_button()])
        prompt = "Choose a maximum resolution" if self.playlist_id else "Choose a YouTube stream"
        await self.create_or_update_control_message(f"{prompt} {self._gen_device_str()}", buttons)

    async def handle_stream_selection(self, action: str):
        async with self._playback_lock:
            if self.playing_videos.is_playing(self):
                return
            notice = None
            try:
                if action == "menu":
                    await self._show_stream_menu()
                    return
                if action.startswith("pick"):
                    value = action.removeprefix("pick")
                    options = await self._get_stream_options() if value else [AUTO_STREAM]
                    choice = next((option for option in options if option.value == value), None)
                    if choice is None:
                        raise YouTubeRelayError("This YouTube stream is unavailable. Use STREAM to pick another.")
                    self._stream_choice = choice
            except YouTubeRelayError as error:
                notice = str(error)
            await self.send_stopped_control_message(notice=notice)

    def _gen_device_str(self):
        return (
            f"on device <code>"
            f"{html.escape(self.playing_device.get_device_name()) if self.playing_device else 'NONE'}</code>"
        )

    @classmethod
    def parse_device_str(cls, text):
        controller, _, _ = (text or "").rpartition(_STREAM_LINE)
        _, separator, name = (controller or text or "").partition(" on device ")
        if not separator:
            return None
        if text.startswith("Streaming closed "):
            name = re.sub(r", [0-9]+\.[0-9]{2}% remains$", "", name)
        return name

    def _gen_message_str(self):
        if self.playlist_id:
            if self._playlist_index is not None:
                return f"for YouTube playlist, item {self._playlist_index}"
            return "for YouTube playlist"
        if self.youtube_id:
            return f"for YouTube video <code>{self.youtube_id}</code>"
        return f"for file <code>{self.video_message.id}</code>"

    async def send_stopped_control_message(self, remaining=None, notice=None):
        buttons = [
            [DeviceButton(self).get_button()],
            [PlayButton(self).get_button()],
        ]
        if self.is_youtube:
            buttons.append([StreamButton(self).get_button()])
        if not remaining:
            text = f"Controller {self._gen_message_str()} {self._gen_device_str()}"
        else:
            text = f"Streaming closed {self._gen_message_str()} {self._gen_device_str()}, {remaining:0.2f}% remains"
        if notice:
            text = f"{text}\n{html.escape(notice)}"
        await self.create_or_update_control_message(text, buttons)

    async def send_playing_control_message(self):
        buttons = [
            [StopButton(self).get_button()],
            [PauseButton(self).get_button()],
        ]
        text = f"Playing {self._gen_message_str()} {self._gen_device_str()}"
        await self.create_or_update_control_message(text, buttons)

    async def send_paused_control_message(self):
        buttons = [
            [StopButton(self).get_button()],
            [ResumeButton(self).get_button()],
        ]
        text = f"Paused {self._gen_message_str()} {self._gen_device_str()}"
        await self.create_or_update_control_message(text, buttons)

    async def send_select_device_message(self, devices):
        device_buttons = [
            [DeviceSelectButton(device.get_device_name(), self, device_id=device.get_device_id()).get_button()]
            for device in devices
        ]
        refresh_button = [[RefreshButton(self).get_button()]]
        await self.create_or_update_control_message("Select a device", device_buttons + refresh_button)

    async def create_or_update_control_message(self, text, buttons):
        if self.is_youtube:
            text += _STREAM_LINE + html.escape(self._stream_choice.label)
        if self.control_message:
            try:
                await self.control_message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
            except MessageNotModified:
                pass
        else:
            self.control_message = await self.video_message.reply(text, reply_markup=InlineKeyboardMarkup(buttons))

    async def play(self):
        async with self._playback_lock:
            if not self.playing_device:
                raise NoDeviceException
            if self.playlist_id:
                max_height = int(self._stream_choice.value) if self._stream_choice.value else None
                await self.playing_videos.play_playlist(self, self.playing_device, self.playlist_id, max_height)
                return
            if self.youtube_id:
                await self._play_youtube()
            else:
                await self._play_telegram_video()
            await self.send_playing_control_message()

    async def show_playlist_item(self, index: int):
        self._playlist_index = index
        await self.send_playing_control_message()

    async def finish_playlist(self, notice: str | None):
        self._playlist_index = None
        await self.send_stopped_control_message(notice=notice)

    async def _play_telegram_video(self):
        try:
            filename = self.pyrogram_filename(self.video_message)
        except TypeError:
            filename = "None"

        await self.playing_videos.interrupt_playlist(self.playing_device)
        await self.playing_device.stop()
        uri = self.playing_videos.add_to_http(self)
        await self.playing_device.play(uri, str(filename), self.local_token)

    async def _play_youtube(self):
        device = self.playing_device
        if self._stream_choice.value:
            upstream = await resolve_youtube_stream(self.youtube_id, format_id=self._stream_choice.value)
        else:
            upstream = await resolve_youtube_stream(self.youtube_id)
        await self.playing_videos.interrupt_playlist(device)
        await device.stop()
        self._remove_youtube_playback()
        relay = YouTubePlayback(self)
        self._youtube_playback = relay
        uri = self.playing_videos.add_to_http(self, upstream, relay=relay)
        try:
            await device.play(uri, upstream.title, relay.local_token)
        except (Exception, asyncio.CancelledError):
            self._remove_youtube_playback()
            raise

    def _remove_youtube_playback(self):
        if self._youtube_playback is not None:
            token = self._youtube_playback.local_token
            self._youtube_playback = None
            self.playing_videos.remove_from_http(token)

    async def stop(self):
        async with self._playback_lock:
            if self.playlist_id and self.playing_device:
                if await self.playing_videos.interrupt_playlist(self.playing_device, owner=self):
                    await self.playing_device.stop()
                else:
                    await self.finish_playlist(None)
                return
            if self.youtube_id:
                self._remove_youtube_playback()
            if self.playing_device:
                # noinspection PyBroadException
                try:
                    if self.playing_videos:
                        await self.playing_videos.interrupt_playlist(self.playing_device)
                    await self.playing_device.stop()
                except Exception:
                    # make sure stop always succeeds even if the device is gone
                    logging.exception("Failed to stop device %r", self.playing_device)
            await self.send_stopped_control_message()
            if not self.playing_device:
                raise NoDeviceException

    async def pause(self):
        if not self.playing_device:
            raise NoDeviceException
        if hasattr(self.playing_device, "pause"):
            await self.playing_device.pause()
            return await self.send_paused_control_message()
        raise ActionNotSupportedException

    async def resume(self):
        if not self.playing_device:
            raise NoDeviceException
        if hasattr(self.playing_device, "resume"):
            await self.playing_device.resume()
            return await self.send_playing_control_message()
        raise ActionNotSupportedException

    async def close(self, remains, *, relay: YouTubePlayback | None = None):
        async with self._playback_lock:
            token = self.local_token
            if relay is not None:
                if self._youtube_playback is not relay:
                    return
                self._youtube_playback = None
                token = relay.local_token
            try:
                await self.send_stopped_control_message(remaining=remains)
                if not self.playing_videos.has_active_playlist(self.playing_device):
                    await self.playing_device.on_close(token)
            finally:
                self.playing_videos.remove(self)

    async def select_device(self, device: Device):
        async with self._playback_lock:
            self.playing_device = device
            self.playing_videos.set_user_device(self.user_id, device)
            await self.send_stopped_control_message()

    @staticmethod
    def pyrogram_filename(message: Message) -> str:
        for media_type in ("document", "video", "audio", "video_note", "animation"):
            media = getattr(message, media_type, None)
            filename = getattr(media, "file_name", None)
            if filename:
                return filename
            if media_type == "video_note" and media is not None:
                return f"video_note_{message.id}.mp4"
        raise TypeError()
