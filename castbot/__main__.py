import argparse
import asyncio
import logging
import sys
import traceback

import aiohttp

try:
    import tomllib
except ImportError:
    import toml as tomllib

from castbot import Http, Bot, DeviceFinderCollection, Downloader


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
    http = Http(config["http"], device_finder)
    downloader = Downloader(config.get("downloader", {}))
    bot = Bot(config["bot"], downloader, http, device_finder)
    http.set_bot(bot)

    await asyncio.gather(bot.start(), http.start())


async def health_check(config):
    url = f"http://{config['http']['listen_host']}:{config['http']['listen_port']}/healthcheck"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url):
                pass
    except Exception:
        traceback.print_exc()
        return 1

    return 0


def entry_point():
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--config", type=lambda x: tomllib.load(open(x, "rb")), default="config.toml")
    parser.add_argument("-v", "--verbose", action="count", default=0)
    parser.add_argument("-hc", "--healthcheck", type=bool, default=False, const=True, nargs="?")

    args = parser.parse_args()

    if args.verbose == 0:
        logging.basicConfig(level=logging.ERROR)
    elif args.verbose == 1:
        logging.basicConfig(level=logging.INFO)
    else:
        logging.basicConfig(level=logging.DEBUG)

    if args.healthcheck:
        sys.exit(asyncio.run(health_check(args.config)))

    asyncio.get_event_loop().run_until_complete(async_main(args.config))


if __name__ == "__main__":
    entry_point()
