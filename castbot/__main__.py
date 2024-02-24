import argparse
import asyncio
import logging
import sys

import aiohttp

try:
    import tomllib
except ImportError:
    import toml as tomllib

from castbot import Http, Bot, DeviceFinderCollection, Downloader, PlayingVideos, BotClient


def open_config(parser: argparse.ArgumentParser, arg: str):
    try:
        return tomllib.load(open(arg, "rb"))
    except FileNotFoundError:
        return parser.error(f"The file `{arg}` does not exist")
    except IsADirectoryError:
        return parser.error(f"`{arg}` is not a file")
    except tomllib.TOMLDecodeError as err:
        return parser.error(f"config file parsing error:\n{str(err)}")
    except ValueError as err:
        return parser.error(str(err))
    except KeyError as err:
        return parser.error(f"config key {str(err)} does not exists")


async def async_main(config):
    device_finder = DeviceFinderCollection(config["devices"])
    bot_client = BotClient(config["bot"])
    http = Http(config["http"], bot_client, device_finder.get_all_routers())
    downloader = Downloader(config.get("downloader", {}))
    playing_videos = PlayingVideos(http)
    bot = Bot(config["bot"], downloader, bot_client, playing_videos, device_finder)

    await asyncio.gather(bot.start(), http.start())


async def health_check(config):
    url = f"http://{config['http']['listen_host']}:{config['http']['listen_port']}/healthcheck"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url):
                pass
    except Exception:
        logging.exception("Failed health check")
        return 1

    return 0


def entry_point():
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--config", type=lambda x: open_config(parser, x), default="config.toml")
    parser.add_argument("-v", "--verbose", action="count")
    parser.add_argument("-hc", "--healthcheck", type=bool, default=False, const=True, nargs="?")
    args = parser.parse_args()

    if args.verbose == 0:
        logging.basicConfig(level=logging.ERROR)
    elif args.verbose == 1:
        logging.basicConfig(level=logging.WARNING)
    elif args.verbose == 2:
        logging.basicConfig(level=logging.INFO)
    else:
        logging.basicConfig(level=logging.DEBUG)

    # pyrogram logging is too verbose
    logging.getLogger("pyrogram").setLevel(logging.WARNING)

    if args.healthcheck:
        sys.exit(asyncio.run(health_check(args.config)))

    asyncio.get_event_loop().run_until_complete(async_main(args.config))


if __name__ == "__main__":
    entry_point()
