from __future__ import annotations

import re
from typing import Any, Mapping, Optional

_GRAPH_NAME_RE = re.compile(r"[^A-Za-z0-9_]")
NODE_RESERVED_PROPERTIES = frozenset(
    {
        "kg_key",
        "id",
        "user_id",
        "organization_id",
        "type",
        "node_type",
        "created_at",
        "updated_at",
        "deleted_at",
        "name",
        "external_ref",
    }
)
EDGE_RESERVED_PROPERTIES = frozenset(
    {
        "kg_key",
        "id",
        "user_id",
        "organization_id",
        "type",
        "edge_type",
        "created_at",
        "updated_at",
        "deleted_at",
        "weight",
        "confidence",
        "evidence_id",
        "evidence_ids",
        "evidence_ids_json",
        "source",
    }
)


def sanitize_graph_name(value: str, *, fallback: str) -> str:
    text = _GRAPH_NAME_RE.sub("_", str(value or "").strip())
    if not text:
        return fallback
    if text[0].isdigit():
        text = f"_{text}"
    return text


def optional_scope_clause(alias: str, organization_id: Optional[int]) -> str:
    return f" AND {alias}.organization_id = $organization_id"


def identity_pattern(alias: str, include_organization: bool) -> str:
    base = f"{alias}.id = ${alias}_id AND {alias}.user_id = ${alias}_user_id"
    return f"{base} AND {alias}.organization_id = ${alias}_organization_id"


def user_properties(
    properties: Mapping[str, Any] | None,
    reserved_properties: frozenset[str],
) -> dict[str, Any]:
    return {
        str(key): value
        for key, value in dict(properties or {}).items()
        if str(key) not in reserved_properties
    }


def node_user_properties(properties: Mapping[str, Any] | None) -> dict[str, Any]:
    return user_properties(properties, NODE_RESERVED_PROPERTIES)


def edge_user_properties(properties: Mapping[str, Any] | None) -> dict[str, Any]:
    return user_properties(properties, EDGE_RESERVED_PROPERTIES)
