import secrets

__all__ = [
    "secret_token",
    "serialize_token",
    "ConfigError",
    "NoDeviceException",
    "ActionNotSupportedException",
    "UnknownCallbackException"
]


def secret_token(nbytes: int = 8) -> int:
    return int.from_bytes(secrets.token_bytes(nbytes=nbytes), "big")


def serialize_token(message_id: int, token: int) -> int:
    return (token << 64) ^ message_id


class NoDeviceException(Exception):
    pass


class ActionNotSupportedException(Exception):
    pass


class UnknownCallbackException(Exception):
    pass


class ConfigError(Exception):
    pass
