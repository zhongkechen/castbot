# CastBot

A Telegram Bot to stream contents (Telegram videos, Youtube videos and more) to your smart TV

[![Flake8](https://github.com/zhongkechen/castbot/actions/workflows/flake8.yml/badge.svg)](https://github.com/zhongkechen/castbot/actions/workflows/flake8.yml)
[![Pylint](https://github.com/zhongkechen/castbot/actions/workflows/pylint.yml/badge.svg)](https://github.com/zhongkechen/castbot/actions/workflows/pylint.yml)
[![PyPI](https://github.com/zhongkechen/castbot/actions/workflows/python-publish.yml/badge.svg)](https://github.com/zhongkechen/castbot/actions/workflows/python-publish.yml)
[![Docker Image on Github](https://github.com/zhongkechen/castbot/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/zhongkechen/castbot/actions/workflows/docker-publish.yml)
[![Docker Image on DockerHub and GHCR](https://github.com/zhongkechen/castbot/actions/workflows/docker.yml/badge.svg)](https://github.com/zhongkechen/castbot/actions/workflows/docker.yml)

### Demonstration video
[![poc](https://i.ibb.co/ct8Qb3z/Screenshot-20200827-200637.png)](https://player.vimeo.com/video/452289383)


## Feature
- Stream Telegram videos to any device that supports UPnP (AVTransport), Chromecast, Vlc (telnet api), Kodi (xbmc http api)
- Stream YouTube videos and playlists through CastBot to any configured playback device
- Web interface that plays videos in your browser
- Download videos by URLs and stream to devices

Send a YouTube video link to the bot, choose a device and press **PLAY**. The player fetches video from CastBot over HTTP as it plays. The bot uses yt-dlp to resolve an MP4 with H.264 video and AAC audio. Availability depends on the formats YouTube offers for each video. If playback fails, stop playback and press **PLAY** to resolve a fresh media URL. For installations outside Docker, make Deno available on the bot's `PATH` for yt-dlp's YouTube support.

Send a YouTube playlist link (`https://www.youtube.com/playlist?list=…`) to play it in order. CastBot resolves each video as it reaches that item, skips entries without a compatible MP4, and advances when the device finishes playing. **STOP** cancels the queue.

Use **STREAM** before pressing **PLAY** to choose a compatible format for a video or a maximum resolution for a playlist. **Auto** selects the best compatible stream. To change the selection during playback, press **STOP** first.

## Known issues

- Chromecast (1st, 2nd and 3rd Gen.) [only supports H.264 and VP8 video codecs](https://developers.google.com/cast/docs/media#video_codecs)
- Most LG TVs with WebOS have an incorrect UPnP implementation
- This bot supports videos of ~4.5Mb/s bit rate at maximum. The videos of higher bit rate would keep freezing.

## How to run castbot with pip

Create a configuration file `config.toml` and then run the following command

```bash
pip install castbot
castbot -c config.toml -v
```

Note: Make sure you have a version of Python 3.11+

## How to run castbot with Docker

Create a configuration file `config.toml` and then run the following command

```bash
docker run --network host -v "$(pwd)/config.toml:/app/config.toml:ro" -d ghcr.io/zhongkechen/castbot:master
```

## How to config

Create a file `config.toml` with the following content

```toml
[downloader]
# Use yt-dlp or you-get to download Youtube videos
downloader = "yt-dlp"

# how many concurrent downloads
concurrency = 10

[bot]

# `api_id` and `api_hash` can be generated here: https://core.telegram.org/api/obtaining_api_id
api_id=652324
api_hash="eb06d4abfb49dc3eeb1aeb9f581e"

# `token` can be created from https://telegram.me/BotFather
token="xxxxxxxxx"

# `session_name` can be an arbitary string.
session_name="castbot"

# Only users in this `admins` list can use this bot. 
# Your own user id can be found here https://telegram.me/getuseridbot
admins=[337885031,32432424,44353421]

[http]

# The IP address or the hostname of the host running castbot
listen_host = "192.168.1.2"

# An arbitary port that is not in use
listen_port = 8350


# The following devices sections are optional. Add the sections you need.

[[devices]]
# When this section is added, all the UPNP devices in the local network will be auto-discovered.
# For Kodi, UPNP must be enabled in Settings -> Services -> UPNP/DLNA
# https://kodi.wiki/view/Settings/Services/UPnP_DLNA
type="upnp"

[[devices]]
# When this section is added, all the ChromeCast devices in the local network will be auto-discovered.
type="chromecast"

[[devices]]
# When this section is added, open http://`listen_host`:`listen_port`/static/index.html in a browser.
# Now if you send a video to the bot, you can choose to play it in the browser
type="web"
password="changeit"

[[devices]]
# When this section is added, we can play video on a device running VLC.
# VLC Telnet interface must be enabled.
type="vlc"
host = "127.0.0.1"
port = 4212
password = "123"

[[devices]]
# When UPNP is blocked by firewall, we can use this section to connect to Kodi.
# Remote Control of Kodi must be enabled: Settings -> Services -> Control.
# https://kodi.wiki/view/Settings/Services/Control
type="xbmc"
host = "192.168.42.140"
port = 8080
username = ""
password = ""
```
