from __future__ import annotations

from importlib import import_module

__all__ = [
    "SDK",
    "active_sdk",
    "current_sdk",
]


def __getattr__(name: str):
    if name not in __all__:
        raise AttributeError(name)
    client = import_module("democrai.sdk.client")
    value = getattr(client, name)
    globals()[name] = value
    return value
