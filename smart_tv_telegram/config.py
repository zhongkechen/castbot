try:
    import tomllib
except ImportError:
    import toml as tomllib


__all__ = ["Config"]


class Config:
    downloader: str = "youtube-dl"

    def __init__(self, path: str):
        config = tomllib.load(open(path, "rb"))

        self.api_id = int(config["mtproto"]["api_id"])
        self.api_hash = str(config["mtproto"]["api_hash"])
        self.token = str(config["mtproto"]["token"])
        self.session_name = str(config["mtproto"]["session_name"])
        self.file_fake_fw_wait = float(config["mtproto"]["file_fake_fw_wait"])

        self.listen_port = int(config["http"]["listen_port"])
        self.listen_host = str(config["http"]["listen_host"])

        self.downloader = str(config["bot"]["downloader"])
        self.request_gone_timeout = int(config["bot"]["request_gone_timeout"])

        self.devices = config["devices"]

        self.block_size = int(config["bot"]["block_size"])
        self.admins = config["bot"]["admins"]

        if not isinstance(self.admins, list):
            raise ValueError("admins should be a list")

        if not all(isinstance(x, int) for x in self.admins):
            raise ValueError("admins list should contain only integers")
