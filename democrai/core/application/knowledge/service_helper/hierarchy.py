"""Helpers that infer weak hierarchy relationships between items in a source.

The subsystem supports heterogeneous media, so hierarchy cannot be modeled as a
strict document tree for every source. Instead, this module derives lightweight
parent/child and sibling links from normalized metadata such as item scope,
chapter index, paragraph index, and item position.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class HierarchyEdge:
    """Derived hierarchy edge between two knowledge items."""
    src_item_id: str
    dst_item_id: str
    edge_type: str


@dataclass(frozen=True)
class _ItemState:
    item: Any
    metadata: dict[str, Any]
    scope: str
    source_kind: str
    item_position: int | None
    chapter_index: int | None
    paragraph_index: int | None
    chunk_index: int | None


def build_hierarchy_edges(
    *,
    items: list[Any],
    metadata_load: Callable[[str], dict[str, Any]],
    focus_item_id: str | None = None,
) -> tuple[HierarchyEdge, ...]:
    """Infer hierarchy and sequence edges between items of the same source.

    :param items: Canonical item rows belonging to one source.
    :param metadata_load: Callable used to deserialize ``metadata_json``.
    :param focus_item_id: Optional item identifier limiting the result to edges
        that touch one item and its immediate derived relations.
    """
    states = [_state_for_item(item, metadata_load) for item in items]
    edges: dict[tuple[str, str, str], HierarchyEdge] = {}

    for state in states:
        if focus_item_id is not None and state.item.id != focus_item_id:
            continue
        parent = _find_parent(state, states)
        if parent is not None:
            _add_edge(edges, parent.item.id, state.item.id, "HAS_CHILD")
            _add_edge(edges, state.item.id, parent.item.id, "CHILD_OF")

        previous = _find_previous_sibling(state, states)
        if previous is not None:
            _add_edge(edges, previous.item.id, state.item.id, "NEXT")
            _add_edge(edges, state.item.id, previous.item.id, "PREVIOUS")

    if focus_item_id is not None:
        for state in states:
            if state.item.id == focus_item_id:
                continue
            parent = _find_parent(state, states)
            previous = _find_previous_sibling(state, states)
            if parent is not None and parent.item.id == focus_item_id:
                _add_edge(edges, parent.item.id, state.item.id, "HAS_CHILD")
                _add_edge(edges, state.item.id, parent.item.id, "CHILD_OF")
            if previous is not None and previous.item.id == focus_item_id:
                _add_edge(edges, previous.item.id, state.item.id, "NEXT")
                _add_edge(edges, state.item.id, previous.item.id, "PREVIOUS")

    return tuple(edges.values())


def _state_for_item(item: Any, metadata_load: Callable[[str], dict[str, Any]]) -> _ItemState:
    metadata = metadata_load(getattr(item, "metadata_json", "") or "")
    if not isinstance(metadata, dict):
        metadata = {}
    return _ItemState(
        item=item,
        metadata=metadata,
        scope=str(metadata.get("item_scope") or "").strip().lower() or "raw",
        source_kind=str(metadata.get("source_kind") or "").strip().lower() or "document",
        item_position=_int_or_none(metadata.get("item_position")),
        chapter_index=_int_or_none(metadata.get("chapter_index")),
        paragraph_index=_int_or_none(metadata.get("paragraph_index")),
        chunk_index=_int_or_none(metadata.get("chunk_index")),
    )


def _find_parent(state: _ItemState, states: list[_ItemState]) -> _ItemState | None:
    if state.scope in {"document", "summary", "index", "message"}:
        return None
    candidates = [candidate for candidate in states if candidate.item.id != state.item.id]
    if state.scope == "chapter":
        return _pick_first(candidates, scopes={"document", "summary"})
    if state.scope == "paragraph":
        return _pick_first(
            candidates,
            scopes={"chapter"},
            chapter_index=state.chapter_index,
        ) or _pick_first(candidates, scopes={"document", "summary"})
    if state.scope in {"chunk", "paragraph_chunk", "raw"}:
        return (
            _pick_first(
                candidates,
                scopes={"paragraph"},
                chapter_index=state.chapter_index,
                paragraph_index=state.paragraph_index,
            )
            or _pick_first(
                candidates,
                scopes={"chapter"},
                chapter_index=state.chapter_index,
            )
            or _pick_first(candidates, scopes={"document", "summary", "transcript"})
        )
    if state.scope in {"segment", "transcript"}:
        return _pick_first(candidates, scopes={"document", "summary", "transcript"})
    return None


def _find_previous_sibling(state: _ItemState, states: list[_ItemState]) -> _ItemState | None:
    candidates = [
        candidate
        for candidate in states
        if candidate.item.id != state.item.id and _same_next_group(candidate, state)
    ]
    if not candidates:
        return None
    ordered = sorted(candidates + [state], key=_ordering_key)
    current_index = ordered.index(state)
    if current_index <= 0:
        return None
    return ordered[current_index - 1]


def _same_next_group(left: _ItemState, right: _ItemState) -> bool:
    return (
        left.scope == right.scope
        and left.source_kind == right.source_kind
        and left.chapter_index == right.chapter_index
        and left.paragraph_index == right.paragraph_index
    )


def _pick_first(
    candidates: list[_ItemState],
    *,
    scopes: set[str],
    chapter_index: int | None = None,
    paragraph_index: int | None = None,
) -> _ItemState | None:
    filtered = [
        candidate
        for candidate in candidates
        if candidate.scope in scopes
        and (chapter_index is None or candidate.chapter_index == chapter_index)
        and (paragraph_index is None or candidate.paragraph_index == paragraph_index)
    ]
    if not filtered:
        return None
    return sorted(filtered, key=_ordering_key)[0]


def _ordering_key(state: _ItemState) -> tuple[int, int, int, str]:
    return (
        state.item_position if state.item_position is not None else 10_000,
        state.paragraph_index if state.paragraph_index is not None else 10_000,
        state.chunk_index if state.chunk_index is not None else 10_000,
        str(state.item.id),
    )


def _int_or_none(value: Any) -> int | None:
    try:
        if value in (None, ""):
            return None
        return int(value)
    except Exception:
        return None


def _add_edge(
    registry: dict[tuple[str, str, str], HierarchyEdge],
    src_item_id: str,
    dst_item_id: str,
    edge_type: str,
) -> None:
    registry[(src_item_id, dst_item_id, edge_type)] = HierarchyEdge(
        src_item_id=src_item_id,
        dst_item_id=dst_item_id,
        edge_type=edge_type,
    )
