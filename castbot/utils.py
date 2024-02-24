import secrets
from typing import Optional, Union

__all__ = [
    "secret_token",
    "ConfigError",
    "NoDeviceException",
    "ActionNotSupportedException",
    "UnknownCallbackException",
    "LocalToken"
]


class LocalToken:
    def __init__(self, message_id: Union[str, int], token: Optional[Union[str, int]] = None):
        self.message_id = int(message_id)
        self.token = int(token or secret_token())

    def __hash__(self):
        return (self.message_id << 64) ^ self.token

    def __eq__(self, other):
        return isinstance(other, LocalToken) and self.__hash__() == other.__hash__()

    def __str__(self):
        return format(self.__hash__(), "x")

    @classmethod
    def deserialize(cls, local_token_raw: Union[int, str]):
        local_token = int(local_token_raw, 16)
        return LocalToken(local_token >> 64, local_token & ~(~0 << 64))


def secret_token(nbytes: int = 8) -> int:
    return int.from_bytes(secrets.token_bytes(nbytes=nbytes))


class NoDeviceException(Exception):
    pass


class ActionNotSupportedException(Exception):
    pass


class UnknownCallbackException(Exception):
    pass


class ConfigError(Exception):
    pass
