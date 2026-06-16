from __future__ import annotations

from importlib import import_module
from typing import Any, Callable, Generic, TypeVar

from democrai.core.runtime.foundation.app import app_ctx

T = TypeVar("T")
ProviderEntry = type[T] | str | Callable[[], type[T]]


class _RegistryFactory(Generic[T]):
    def __init__(self, fallback_name: str, fallback_entry: ProviderEntry[T]) -> None:
        self._fallback_name = fallback_name
        self._registry: dict[str, ProviderEntry[T]] = {fallback_name: fallback_entry}

    def register(self, name: str, provider_entry: ProviderEntry[T]) -> None:
        self._registry[str(name).strip().lower()] = provider_entry

    def create(
        self, provider_type: str | None, *, strict: bool = False, **kwargs: Any
    ) -> T:
        raw_provider_type = "" if provider_type is None else str(provider_type).strip()
        normalized = (
            self._fallback_name if not raw_provider_type else raw_provider_type.lower()
        )
        entry = self._registry.get(normalized)
        if entry is None and ":" in raw_provider_type:
            entry = raw_provider_type
        if entry is None:
            if strict:
                raise ValueError(f"provider_type_unknown:{provider_type}")
            app_ctx().logger.warning(
                f"Provider type '{provider_type}' not found. Falling back to "
                f"'{self._fallback_name}'."
            )
            normalized = self._fallback_name
            entry = self._registry[self._fallback_name]
        provider_cls = self._resolve_entry(entry)
        return provider_cls(**kwargs)

    @staticmethod
    def _resolve_entry(entry: ProviderEntry[T]) -> type[T]:
        if isinstance(entry, str):
            module_name, _, attr_name = entry.partition(":")
            module = import_module(module_name)
            return getattr(module, attr_name)
        if isinstance(entry, type):
            return entry
        resolved = entry()
        if not isinstance(resolved, type):
            raise TypeError("provider resolver must return a class")
        return resolved
