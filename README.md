# smart-tv-telegram

A Telegram Bot to stream contents (Telegram videos, Youtube videos and more) to your smart TV

### Demonstration video
[![poc](https://i.ibb.co/ct8Qb3z/Screenshot-20200827-200637.png)](https://player.vimeo.com/video/452289383)


## Feature
- Stream Telegram videos to any device that supports UPnP (AVTransport), Chromecast, Vlc (telnet api), Kodi (xbmc http api)
- Web interface that plays videos in your browser
- Download videos by URLs and stream to devices

## Known issues

- Chromecast (1st, 2nd and 3rd Gen.) [only supports H.264 and VP8 video codecs](https://developers.google.com/cast/docs/media#video_codecs)
- Most LG TVs with WebOS have an incorrect UPnP implementation

## How-to setup (Release from pypi)
Make sure you have an updated version of python, only the latest version will be supported

- Install Poetry if it's not installed yet
- Clone the repository
- Install python dependencies
- Copy config.ini.example to config.ini
- Edit config.ini
- Start from python entrypoint

```bash
# install poetry
curl -sSL https://install.python-poetry.org | python3 -

git clone https://github.com/andrew-ld/smart-tv-telegram
cd smart-tv-telegram
poetry install
cp config.toml.example config.toml
nano config.toml
poetry run smart_tv_telegram -c config.toml -v 1
```

## How-to setup (Docker)
- Copy config.ini.example to config.ini
- Edit config.ini
- Build Docker image
- Start Docker container

```bash
cp config.toml.example config.toml
nano config.toml
docker image build -t smart-tv-telegram:latest .
docker run --network host -v "$(pwd)/config.ini:/app/config.ini:ro" -d smart-tv-telegram:latest
```

## FAQ

**Q:** How do I use the web interface?

**A:** Set `enabled` to `1` in `web_ui` config block, and change the `password`

- open http://`listen_ip`:`listen_port`/static/index.html

- now if you send a video in the bot on telegram you can choose to play it in the browser

##
**Q:** My Firewall block upnp and broadcasting, how can use kodi without it

**A:** Set `xbmc_enabled` to `1` and add your kodi device to `xbmc_devices` list

##
**Q:** What is the format of `xbmc_devices`

**A:** A List of Python Dict with `host`, `port`, (and optional: `username` and `password`)

**example:** `[{"host": "192.168.1.2", "port": 8080, "username": "pippo", "password": "pluto"}]`

##
**Q:** How-To control vlc from this bot

**A:** set `vlc_enabled` to `1` and add your vlc device to `vlc_devices` list

##
**Q:** What is the format of `vlc_devices`

**A:** A List of Python Dict with `host`, `port`, (and optional: `password`)

**example:** `[{"host": "127.0.0.1", "port": 4212, "password": "123"}]`


##
**Q:** How-To enable upnp on my device that use kodi

**A:** follow [this guide](https://kodi.wiki/view/Settings/Services/UPnP_DLNA) (you should enable remote control)

##
**Q:** How do I get a token?

**A:** From [@BotFather](https://telegram.me/BotFather)
##
**Q:** How do I set up admins?

**A:** You have to enter your user_id, there are many ways to get it, the easiest is to use [@getuseridbot](https://telegram.me/getuseridbot)
##
**Q:** How do I get an app_id and app_hash?

**A:** https://core.telegram.org/api/obtaining_api_id#obtaining-api-id
##
**Q:** The video keeps freezing

**A:** Check the video bitrate, this bot supports maximum ~4.5Mb/s
