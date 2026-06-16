from __future__ import annotations

__all__ = ["Network"]


def __getattr__(name: str):
    if name == "Network":
        from democrai.core.infrastructure.network.runtime import Network

        return Network
    raise AttributeError(name)
