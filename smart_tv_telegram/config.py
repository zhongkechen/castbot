import ast
import configparser
import typing

__all__ = [
    "Config"
]


class Config:
    api_id: int
    api_hash: str
    token: str
    session_name: str
    file_fake_fw_wait: float

    device_request_timeout: int

    listen_host: str
    listen_port: int

    upnp_enabled: bool
    upnp_scan_timeout: int = 0

    chromecast_enabled: bool
    chromecast_scan_timeout: int = 0

    web_ui_enabled: bool
    web_ui_password: str = ""

    xbmc_enabled: bool
    xbmc_devices: typing.List[dict]

    vlc_enabled: bool
    vlc_devices: typing.List[dict]

    request_gone_timeout: int

    admins: typing.List[int]
    block_size: int

    def __init__(self, path: str):
        config = configparser.ConfigParser()
        config.read(path)

        self.api_id = int(config["mtproto"]["api_id"])
        self.api_hash = str(config["mtproto"]["api_hash"])
        self.token = str(config["mtproto"]["token"])
        self.session_name = str(config["mtproto"]["session_name"])
        self.file_fake_fw_wait = float(config["mtproto"]["file_fake_fw_wait"])

        self.listen_port = int(config["http"]["listen_port"])
        self.listen_host = str(config["http"]["listen_host"])

        self.request_gone_timeout = int(config["bot"]["request_gone_timeout"])
        self.device_request_timeout = int(config["discovery"]["device_request_timeout"])

        self.upnp_enabled = bool(int(config["discovery"]["upnp_enabled"]))

        if self.upnp_enabled:
            self.upnp_scan_timeout = int(config["discovery"]["upnp_scan_timeout"])

            if self.upnp_scan_timeout > self.device_request_timeout:
                raise ValueError("upnp_scan_timeout should < device_request_timeout")

        self.web_ui_enabled = bool(int(config["web_ui"]["enabled"]))

        if self.web_ui_enabled:
            self.web_ui_password = config["web_ui"]["password"]

        self.chromecast_enabled = bool(int(config["discovery"]["chromecast_enabled"]))

        self.xbmc_enabled = bool(int(config["discovery"]["xbmc_enabled"]))

        if self.xbmc_enabled:
            self.xbmc_devices = ast.literal_eval(config["discovery"]["xbmc_devices"])

            if not isinstance(self.xbmc_devices, list):
                raise ValueError("xbmc_devices should be a list")

            if not all(isinstance(x, dict) for x in self.xbmc_devices):
                raise ValueError("xbmc_devices should contain only dict")

        else:
            self.xbmc_devices = []

        self.vlc_enabled = bool(int(config["discovery"]["vlc_enabled"]))

        if self.vlc_enabled:
            self.vlc_devices = ast.literal_eval(config["discovery"]["vlc_devices"])

            if not isinstance(self.xbmc_devices, list):
                raise ValueError("vlc_devices should be a list")

            if not all(isinstance(x, dict) for x in self.xbmc_devices):
                raise ValueError("vlc_devices should contain only dict")

        else:
            self.vlc_devices = []

        if self.chromecast_enabled:
            self.chromecast_scan_timeout = int(config["discovery"]["chromecast_scan_timeout"])

            if self.chromecast_scan_timeout > self.device_request_timeout:
                raise ValueError("chromecast_scan_timeout should < device_request_timeout")

        self.admins = ast.literal_eval(config["bot"]["admins"])
        self.block_size = int(config["bot"]["block_size"])

        if not isinstance(self.admins, list):
            raise ValueError("admins should be a list")

        if not all(isinstance(x, int) for x in self.admins):
            raise ValueError("admins list should contain only integers")
