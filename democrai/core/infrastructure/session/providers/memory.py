from __future__ import annotations


class MemoryJsonStore:
    def __init__(self) -> None:
        self._items: dict[str, dict[str, object]] = {}

    def load(self, key: str) -> dict[str, object] | None:
        value = self._items.get(key)
        return dict(value) if value is not None else None

    def save(self, key: str, value: dict[str, object]) -> None:
        self._items[key] = dict(value)

    def delete(self, key: str) -> None:
        self._items.pop(key, None)

    def keys(self) -> list[str]:
        return list(self._items.keys())
