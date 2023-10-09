import asyncio
import logging
import argparse
import os.path
import sys

try:
    import tomllib
except ImportError:
    import toml as tomllib
import traceback
import urllib.request

from castbot import Http, Bot, DeviceFinderCollection, Downloader


def open_config(parser: argparse.ArgumentParser, arg: str):
    if not os.path.exists(arg):
        parser.error(f"The file `{arg}` does not exist")
    elif not os.path.isfile(arg):
        parser.error(f"`{arg}` is not a file")

    try:
        return tomllib.load(open(arg, "rb"))
    except tomllib.TOMLDecodeError as err:
        return parser.error(f"config file parsing error:\n{str(err)}")
    except ValueError as err:
        return parser.error(str(err))
    except KeyError as err:
        return parser.error(f"config key {str(err)} does not exists")


async def async_main(config):
    device_finder = DeviceFinderCollection(config["devices"])
    http = Http(config["http"], device_finder)
    downloader = Downloader(config["downloader"])
    bot = Bot(config["bot"], downloader, http, device_finder)
    http.set_bot(bot)

    await bot.start()
    await http.start()


def main(config):
    loop = asyncio.get_event_loop()
    loop.run_until_complete(async_main(config))


def health_check(config):
    # noinspection PyBroadException
    try:
        urllib.request.urlopen(f"http://{config['http']['listen_host']}:{config['http']['listen_port']}/healthcheck")
    except Exception:
        traceback.print_exc()
        return 1

    return 0


def entry_point():
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--config", type=lambda x: open_config(parser, x), default="config.toml")
    parser.add_argument("-v", "--verbosity", type=int, choices=[0, 1, 2], default=0)
    parser.add_argument("-hc", "--healthcheck", type=bool, default=False, const=True, nargs="?")

    args = parser.parse_args()

    if args.verbosity == 0:
        logging.basicConfig(level=logging.ERROR)

    elif args.verbosity == 1:
        logging.basicConfig(level=logging.INFO)

    elif args.verbosity == 2:
        logging.basicConfig(level=logging.DEBUG)

    if args.healthcheck:
        sys.exit(health_check(args.config))

    main(args.config)


if __name__ == "__main__":
    entry_point()
