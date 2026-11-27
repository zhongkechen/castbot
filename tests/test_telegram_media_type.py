import unittest
import xml.etree.ElementTree as ET
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from pyrogram.raw.types import Document, MessageMediaDocument

from castbot.devices.upnp import UpnpDevice, UpnpNotifyServer
from castbot.http import Http
from castbot.utils import LocalToken
from castbot.video import PlayingVideo


class TelegramMediaTypeTest(unittest.IsolatedAsyncioTestCase):
    async def test_head_advertises_the_document_media_type(self):
        document = Document(
            id=7, access_hash=2, file_reference=b"fixture", date=0, mime_type="audio/mpeg",
            size=4, dc_id=1, attributes=[],
        )
        client = SimpleNamespace(get_message=AsyncMock(return_value=SimpleNamespace(
            media=MessageMediaDocument(document=document),
        )))
        server = Http({"listen_host": "127.0.0.1", "listen_port": 8350}, client, [])
        token = LocalToken(10, 2)
        server.add_remote_token(SimpleNamespace(local_token=token))
        request = SimpleNamespace(match_info={"message_id": "10", "token": "2"}, method="HEAD", headers={})

        response = await server._stream_handler(request)
        self.assertEqual(response.status, 200)
        self.assertEqual(response.headers["Content-Type"], "audio/mpeg")

    async def test_audio_playback_advertises_the_media_type_to_upnp(self):
        actions = {
            name: SimpleNamespace(async_call=AsyncMock()) for name in ("SetAVTransportURI", "Play", "Stop")
        }
        service = SimpleNamespace(action=actions.__getitem__)
        receiver = SimpleNamespace(friendly_name="Test TV", udn="uuid:fixture", service=lambda _: service)
        player = UpnpDevice(receiver, UpnpNotifyServer())
        token = LocalToken(10, 2)
        video = PlayingVideo(
            token, 1, SimpleNamespace(
                interrupt_playlist=AsyncMock(), add_to_http=lambda _: "http://castbot.invalid/stream/10/2",
            ),
            playing_device=player,
            video_message=SimpleNamespace(id=10, audio=SimpleNamespace(mime_type="audio/mpeg", file_name="song.mp3")),
            control_message=SimpleNamespace(edit_text=AsyncMock()),
        )
        subscription = SimpleNamespace(start=AsyncMock(), close=AsyncMock())
        with patch("castbot.devices.upnp.SubscribeTask", return_value=subscription):
            await video.play()
            await player.on_close(token)

        metadata = actions["SetAVTransportURI"].async_call.await_args.kwargs["CurrentURIMetaData"]
        root = ET.fromstring(metadata)
        resource = root.find(".//{urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/}res")
        self.assertTrue(resource.attrib["protocolInfo"].startswith("http-get:*:audio/mpeg:"))
        media_class = root.find(".//{urn:schemas-upnp-org:metadata-1-0/upnp/}class")
        self.assertEqual(media_class.text, "object.item.audioItem.musicTrack")
