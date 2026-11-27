import re
import secrets
from typing import Optional, Union

__all__ = [
    "secret_token",
    "normalize_media_type",
    "ConfigError",
    "NoDeviceException",
    "DeviceControlError",
    "ActionNotSupportedException",
    "UnknownCallbackException",
    "LocalToken"
]

_MEDIA_TYPE = re.compile(r"[A-Za-z0-9!#$%&'*+.^_`|~\-]+/[A-Za-z0-9!#$%&'*+.^_`|~\-]+")


def normalize_media_type(value: str | None) -> str | None:
    if isinstance(value, str) and _MEDIA_TYPE.fullmatch(value.strip()):
        return value.strip().lower()
    return None


class LocalToken:
    def __init__(self, message_id: Union[str, int], token: Optional[Union[str, int]] = None):
        self.message_id = int(message_id)
        self.token = secret_token() if token is None else int(token)

    def __hash__(self):
        return hash((self.message_id, self.token))

    def __eq__(self, other):
        return isinstance(other, LocalToken) and (self.message_id, self.token) == (other.message_id, other.token)

    def __str__(self):
        return format((self.message_id << 64) | self.token, "x")

    @classmethod
    def deserialize(cls, local_token_raw: Union[int, str]):
        local_token = int(local_token_raw, 16)
        return LocalToken(local_token >> 64, local_token & ~(~0 << 64))


def secret_token(nbytes: int = 8) -> int:
    return int.from_bytes(secrets.token_bytes(nbytes=nbytes))


class DeviceControlError(Exception):
    pass


class NoDeviceException(Exception):
    pass


class ActionNotSupportedException(Exception):
    pass


class UnknownCallbackException(Exception):
    pass


class ConfigError(Exception):
    pass
