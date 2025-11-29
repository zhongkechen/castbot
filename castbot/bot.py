from pyrogram import filters
from pyrogram.handlers import MessageHandler, CallbackQueryHandler


__all__ = ["Bot"]


class Bot:
    def __init__(
        self,
        config,
        downloader,
        bot_client,
        playing_videos,
        buttons,
    ):
        self._bot_client = bot_client
        self._downloader = downloader
        self._buttons = buttons
        self._admins = config["admins"]
        if not isinstance(self._admins, list):
            raise ValueError("admins should be a list")
        if not all(isinstance(x, int) for x in self._admins):
            raise ValueError("admins list should contain only integers")

        self._playing_videos = playing_videos

    async def start(self):
        admin_filter = filters.chat(self._admins) & filters.private
        self._bot_client.register(MessageHandler(self._playing_videos.on_new_video, filters.document & admin_filter))
        self._bot_client.register(MessageHandler(self._playing_videos.on_new_video, filters.video & admin_filter))
        self._bot_client.register(MessageHandler(self._playing_videos.on_new_video, filters.audio & admin_filter))
        self._bot_client.register(MessageHandler(self._playing_videos.on_new_video, filters.animation & admin_filter))
        self._bot_client.register(MessageHandler(self._playing_videos.on_new_video, filters.voice & admin_filter))
        self._bot_client.register(MessageHandler(self._playing_videos.on_new_video, filters.video_note & admin_filter))
        self._bot_client.register(MessageHandler(self._downloader.on_new_link, filters.text & admin_filter))

        admin_filter_inline = filters.create(lambda _, __, m: m.from_user.id in self._admins)
        self._bot_client.register(CallbackQueryHandler(self._buttons.on_button_click, admin_filter_inline))
        await self._bot_client.start()

