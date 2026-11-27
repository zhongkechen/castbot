import asyncio
import functools
import logging
import os
import pickle
import typing

from async_lru import alru_cache
from pyrogram import Client
from pyrogram.enums import ParseMode
from pyrogram.errors import FileReferenceExpired, FloodWait
from pyrogram.handlers.handler import Handler
from pyrogram.raw.functions.auth import ExportAuthorization, ImportAuthorization
from pyrogram.raw.functions.help import GetConfig
from pyrogram.raw.functions.messages import GetMessages
from pyrogram.raw.functions.upload import GetFile
from pyrogram.raw.types import Document, InputMessageID, Message as RawMessage, InputDocumentFileLocation
from pyrogram.raw.types import MessageMediaDocument
from pyrogram.raw.types.upload import File
from pyrogram.session import Session, Auth
from pyrogram.types import ReplyParameters


class BotClient:
    def __init__(self, config):
        self._session_name = str(config["session_name"])
        self._api_id = int(config["api_id"])
        self._api_hash = str(config["api_hash"])
        self._token = str(config["token"])
        self._file_fake_fw_wait = float(config.get("file_fake_fw_wait", 0.2))

        self._client = Client(
            self._session_name,
            self._api_id,
            self._api_hash,
            bot_token=self._token,
            sleep_threshold=0,
            workdir=os.getcwd(),
        )

    def register(self, handler: Handler):
        self._client.add_handler(handler)

    async def reply_message(self, message_id: int, chat_id: int, text: str):
        await self._client.send_message(
            chat_id,
            text=text,
            parse_mode=ParseMode.HTML,
            reply_parameters=ReplyParameters(message_id=message_id),
        )

    @alru_cache
    async def get_message(self, message_id: int) -> RawMessage:
        messages = await self._client.invoke(GetMessages(id=[InputMessageID(id=message_id)]))

        if not messages.messages:
            raise ValueError("wrong message_id")

        message = messages.messages[0]

        if not isinstance(message, RawMessage):
            raise ValueError(f"expected `Message`, found: `{type(message).__name__}`")

        return message

    async def health_check(self):
        if not all(x.is_started.is_set() for x in self._client.media_sessions.values()):
            logging.log(logging.ERROR, "media session not connected")
            raise ConnectionError()

        if not self._client.session.is_started.is_set():
            logging.log(logging.ERROR, "main session not connected")
            raise ConnectionError()

    async def get_block(self, message: RawMessage, offset: int, block_size: int) -> bytes:
        document = message.media.document
        expired_reference = document.file_reference
        try:
            return await self._get_document_block(document, offset, block_size)
        except FileReferenceExpired:
            latest_message = await self.get_message(message.id)
            reference = self._matching_file_reference(latest_message, document.id)
            if reference == expired_reference:
                self.get_message.cache_invalidate(message.id)
                latest_message = await self.get_message(message.id)
                reference = self._matching_file_reference(latest_message, document.id)
            if reference is None or reference == expired_reference:
                raise
            # Keep streams using the original message on the refreshed reference.
            document.file_reference = reference
            return await self._get_document_block(document, offset, block_size)

    @staticmethod
    def _matching_file_reference(message: RawMessage, document_id: int) -> bytes | None:
        media = message.media
        if isinstance(media, MessageMediaDocument) and isinstance(media.document, Document):
            if media.document.id == document_id:
                return media.document.file_reference
        return None

    async def _get_document_block(self, document: Document, offset: int, block_size: int) -> bytes:
        session = self._client.media_sessions.get(document.dc_id)

        request = GetFile(
            offset=offset,
            limit=block_size,
            location=InputDocumentFileLocation(
                id=document.id,
                access_hash=document.access_hash,
                file_reference=document.file_reference,
                thumb_size="",
            ),
        )

        result: typing.Optional[File] = None

        while not isinstance(result, File):
            try:
                result = await session.invoke(request, sleep_threshold=0)
            except FloodWait:  # file floodwait is fake
                await asyncio.sleep(self._file_fake_fw_wait)

        return result.bytes

    @staticmethod
    def _select_dc_option(dc_options, dc_id: int, ipv6: bool = False):
        options = [dc for dc in dc_options if dc.id == dc_id and bool(dc.ipv6) == ipv6 and not dc.cdn]
        non_tcpo_options = [dc for dc in options if not dc.tcpo_only]
        candidates = non_tcpo_options or options

        prod_options = [dc for dc in candidates if not dc.media_only]
        if prod_options:
            return prod_options[0]

        media_options = [dc for dc in candidates if dc.media_only]
        if media_options:
            return media_options[0]

        return None

    async def start(self):
        await self._client.start()

        config = await self._client.invoke(GetConfig())
        dc_ids = set(x.id for x in config.dc_options if not x.cdn)
        keys_path = self._session_name + ".keys"
        test_mode = bool(await self._client.storage.test_mode())
        ipv6 = bool(getattr(self._client, "ipv6", False))

        if os.path.exists(keys_path):
            keys = pickle.load(open(keys_path, "rb"))
        else:
            keys = {}

        for dc_id in dc_ids:
            dc_option = self._select_dc_option(config.dc_options, dc_id, ipv6=ipv6)
            if dc_option is None:
                continue

            server_address = dc_option.ip_address
            port = dc_option.port

            session = functools.partial(
                Session,
                self._client,
                dc_id,
                server_address,
                port,
                is_media=True,
                test_mode=test_mode,
            )

            if dc_id != await self._client.storage.dc_id():
                if dc_id not in keys:
                    exported_auth = await self._client.invoke(ExportAuthorization(dc_id=dc_id))

                    auth = Auth(self._client, dc_id, server_address, port, test_mode)
                    auth_key = await auth.create()

                    session = session(auth_key)
                    await session.start()

                    await session.invoke(ImportAuthorization(id=exported_auth.id, bytes=exported_auth.bytes))
                    keys[dc_id] = session.auth_key

                else:
                    session = session(keys[dc_id])
                    await session.start()

            else:
                session = session(await self._client.storage.auth_key())
                await session.start()

            self._client.media_sessions[dc_id] = session

        pickle.dump(keys, open(keys_path, "wb"))
        logging.info("Telegram server connected")
