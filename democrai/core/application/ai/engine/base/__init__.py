from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .audio import BaseSTTProvider, BaseTTSProvider
    from .cv import BaseCvProvider
    from .engine import BaseEngine
    from .kg import KGProvider
    from .llm import LLMProvider

__all__ = [
    "BaseEngine",
    "LLMProvider",
    "BaseSTTProvider",
    "BaseTTSProvider",
    "BaseCvProvider",
    "KGProvider",
]


_SYMBOL_MAP = {
    "BaseEngine": (".engine", "BaseEngine"),
    "LLMProvider": (".llm", "LLMProvider"),
    "BaseSTTProvider": (".audio", "BaseSTTProvider"),
    "BaseTTSProvider": (".audio", "BaseTTSProvider"),
    "BaseCvProvider": (".cv", "BaseCvProvider"),
    "KGProvider": (".kg", "KGProvider"),
}


def __getattr__(name: str):
    target = _SYMBOL_MAP.get(name)
    if target is None:
        raise AttributeError(name)

    module_name, attr_name = target
    mod = import_module(module_name, __name__)
    value = getattr(mod, attr_name)
    globals()[name] = value
    return value
