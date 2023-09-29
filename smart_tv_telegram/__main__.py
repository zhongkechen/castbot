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
import typing
import urllib.request

from smart_tv_telegram import Http, Mtproto, Config, Bot, device_finder


def open_config(parser: argparse.ArgumentParser, arg: str) -> typing.Optional[Config]:
    if not os.path.exists(arg):
        parser.error(f"The file `{arg}` does not exist")
    elif not os.path.isfile(arg):
        parser.error(f"`{arg}` is not a file")

    try:
        return Config(arg)
    except tomllib.TOMLDecodeError as err:
        parser.error(f"config file parsing error:\n{str(err)}")
    except ValueError as err:
        parser.error(str(err))
    except KeyError as err:
        parser.error(f"config key {str(err)} does not exists")

    return None


async def async_main(config: Config):
    mtproto = Mtproto(config)
    http = Http(mtproto, config, device_finder)
    bot = Bot(mtproto, config, http, device_finder)

    await mtproto.start()
    await http.start()


def main(config: Config):
    loop = asyncio.get_event_loop()
    loop.run_until_complete(async_main(config))


def health_check(config: Config):
    # noinspection PyBroadException
    try:
        urllib.request.urlopen(f"http://{config.listen_host}:{config.listen_port}/healthcheck")
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
