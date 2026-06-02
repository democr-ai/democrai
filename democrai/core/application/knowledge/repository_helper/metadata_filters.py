"""Portable SQL filters for knowledge metadata JSON."""

from __future__ import annotations

from typing import Any

from sqlalchemy import cast
from sqlalchemy import func
from sqlalchemy import or_
from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSONB


def metadata_filter_expressions(
    session: Any,
    metadata_column: Any,
    filters: dict[str, Any],
):
    """Build DB-specific JSON metadata equality filters.

    Supports scalar equality and list membership. Nested keys are intentionally
    not supported here; callers should store filterable metadata as top-level
    scalar values.
    """
    expressions = []
    if not filters:
        return expressions
    dialect_name = _dialect_name(session)
    for key, raw_value in filters.items():
        values = _filter_values(raw_value)
        if not values:
            continue
        json_value = _json_text_value(
            metadata_column,
            key=key,
            dialect_name=dialect_name,
        )
        if len(values) == 1:
            expressions.append(json_value == values[0])
        else:
            expressions.append(or_(*(json_value == value for value in values)))
    return expressions


def _dialect_name(session: Any) -> str:
    bind = session.get_bind()
    dialect = getattr(bind, "dialect", None)
    return dialect.name


def _filter_values(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (list, tuple, set)):
        return tuple(
            str(item).strip()
            for item in value
            if str(item).strip()
        )
    rendered = str(value).strip()
    return (rendered,) if rendered else ()


def _json_text_value(metadata_column: Any, *, key: str, dialect_name: str):
    if dialect_name == "postgresql":
        return cast(metadata_column, JSONB).op("->>")(key)
    return cast(func.json_extract(metadata_column, f"$.{key}"), String)
