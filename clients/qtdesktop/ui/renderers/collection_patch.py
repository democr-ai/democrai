from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


IdGetter = Callable[[Any], Any]


@dataclass
class CollectionPatchResult:
    handled: bool
    items: list[Any]
    index: int | None = None
    replacement: Any = None
    appended: list[Any] | None = None


def collection_items(value: Any) -> list[Any]:
    return value if isinstance(value, list) else [value]


def resolve_collection_index(
    items: list[Any],
    payload: Any,
    *,
    id_getter: IdGetter | None = None,
) -> int | None:
    if isinstance(payload, int):
        return payload if 0 <= payload < len(items) else None

    if isinstance(payload, dict):
        index_value = payload.get("index")
        if isinstance(index_value, int):
            return index_value if 0 <= index_value < len(items) else None
        target_id = payload.get("id")
    else:
        target_id = payload if isinstance(payload, str) else None

    if target_id is None:
        return None

    for index, item in enumerate(items):
        current_id = (
            id_getter(item)
            if callable(id_getter)
            else (item.get("id") if isinstance(item, dict) else None)
        )
        if current_id is not None and str(current_id) == str(target_id):
            return index
    return None


def replacement_item(payload: Any) -> Any:
    if isinstance(payload, dict):
        return payload.get("item")
    return None


def patch_collection(
    items: list[Any],
    action: str,
    value: Any,
    *,
    id_getter: IdGetter | None = None,
) -> CollectionPatchResult:
    current = list(items)
    if action == "set":
        return CollectionPatchResult(handled=True, items=list(value or []))

    if action == "append":
        appended = collection_items(value)
        return CollectionPatchResult(
            handled=True,
            items=[*current, *appended],
            appended=appended,
        )

    if action == "prepend":
        prepended = collection_items(value)
        return CollectionPatchResult(
            handled=True,
            items=[*prepended, *current],
            appended=prepended,
        )

    if action == "remove":
        index = resolve_collection_index(current, value, id_getter=id_getter)
        if index is None:
            return CollectionPatchResult(handled=True, items=current, index=None)
        current.pop(index)
        return CollectionPatchResult(handled=True, items=current, index=index)

    if action == "replace":
        index = resolve_collection_index(current, value, id_getter=id_getter)
        replacement = replacement_item(value)
        if index is None or replacement is None:
            return CollectionPatchResult(
                handled=True,
                items=current,
                index=index,
                replacement=replacement,
            )
        current[index] = replacement
        return CollectionPatchResult(
            handled=True,
            items=current,
            index=index,
            replacement=replacement,
        )

    return CollectionPatchResult(handled=False, items=current)
