from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_registry: dict[str, Callable] = {}


def _fmt(name: str) -> Callable:
    def decorator(fn: Callable) -> Callable:
        _registry[name] = fn
        return fn
    return decorator


def _lookup_stub_record(
    *,
    app_instance: Any,
    stub_name: str,
    key_value: Any,
) -> dict[str, Any] | None:
    store = getattr(app_instance, "store", None)
    if store is None or not stub_name:
        return None
    rows = store.get(f"/stubs/{stub_name}", [], "global")
    if not isinstance(rows, list):
        return None

    key_text = str(key_value)
    for row in rows:
        if not isinstance(row, dict):
            continue
        candidate = row.get("key")
        if candidate == key_value or str(candidate) == key_text:
            return row
    return None


# ---------------------------------------------------------------------------
# Built-in formatters
# ---------------------------------------------------------------------------

@_fmt("upper")
def _upper(value: Any, **_kwargs) -> str:
    return str(value).upper()


@_fmt("lower")
def _lower(value: Any, **_kwargs) -> str:
    return str(value).lower()


@_fmt("title")
def _title(value: Any, **_kwargs) -> str:
    return str(value).title()


@_fmt("truncate")
def _truncate(value: Any, n: str = "50", **_kwargs) -> str:
    text = str(value)
    try:
        limit = int(n)
        return text[:limit] + "…" if len(text) > limit else text
    except (ValueError, TypeError):
        return text


@_fmt("date")
def _date(value: Any, fmt: str = "%Y-%m-%d", **_kwargs) -> str:
    try:
        return datetime.fromisoformat(str(value)).strftime(fmt)
    except (ValueError, TypeError):
        return str(value)


@_fmt("get_stub")
def _get_stub(
    value: Any,
    stub_name: str = "",
    output_field: str = "value",
    *,
    app_instance: Any = None,
    row: dict[str, Any] | None = None,
) -> str:
    del row
    if app_instance is None or not stub_name:
        return str(value)

    record = _lookup_stub_record(
        app_instance=app_instance,
        stub_name=stub_name,
        key_value=value,
    )
    if not isinstance(record, dict):
        return str(value)

    field_name = str(output_field or "value")
    resolved = record.get(field_name)
    if resolved is None and field_name != "value":
        resolved = record.get("value")
    return str(resolved) if resolved is not None else str(value)


@_fmt("join_list")
def _join_list(value: Any, sep: str = ", ", inner: str = "", **_kwargs) -> str:
    """Join a list of primitive values.

    transform: "join_list|<sep>|<inner_transform>"
    Example:   "join_list|, |upper"  →  "READ, WRITE, ADMIN"
    """
    if not isinstance(value, (list, tuple)):
        return apply_transform(value, None)
    return sep.join(apply_transform(v, inner or None) for v in value)


@_fmt("join_objects")
def _join_objects(
    value: Any,
    key: str = "",
    sep: str = ", ",
    inner: str = "",
    **_kwargs,
) -> str:
    """Join a list of dicts extracting a specific key from each.

    transform: "join_objects|<key>|<sep>|<inner_transform>"
    Example:   "join_objects|name|, |title"  →  "Backend, Platform"
    """
    if not isinstance(value, (list, tuple)):
        return apply_transform(value, None)
    parts: list[str] = []
    for obj in value:
        v = obj.get(key, "") if isinstance(obj, dict) else obj
        parts.append(apply_transform(v, inner or None))
    return sep.join(parts)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def apply_transform(
    value: Any,
    transform: str | None,
    *,
    row: dict[str, Any] | None = None,
    app_instance: Any = None,
) -> str:
    """Format *value* according to *transform*.

    New syntax  — pipe-separated:  "func_name|arg1|arg2|..."
    Legacy syntax — colon-separated (backward compat): "date:%Y-%m-%d", "truncate:20"
    """
    if value is None:
        return ""
    if not transform:
        return str(value)

    # New pipe-separated syntax
    if "|" in transform:
        parts = transform.split("|")
        func_name = parts[0].strip()
        args = parts[1:]
        try:
            fn = _registry.get(func_name)
            if fn is None:
                return str(value)
            return fn(value, *args, app_instance=app_instance, row=row)
        except Exception:
            return str(value)

    # Legacy colon syntax — kept for backward compatibility
    if transform == "upper":
        return str(value).upper()
    if transform == "lower":
        return str(value).lower()
    if transform == "title":
        return str(value).title()
    if transform.startswith("truncate:"):
        try:
            n = int(transform.split(":")[1])
            text = str(value)
            return text[:n] + "…" if len(text) > n else text
        except (ValueError, IndexError):
            return str(value)
    if transform.startswith("date:"):
        fmt = transform.split(":", 1)[1]
        try:
            return datetime.fromisoformat(str(value)).strftime(fmt)
        except (ValueError, TypeError):
            return str(value)
    if transform.startswith("get_stub:"):
        parts = transform.split(":")
        stub_name = parts[1].strip() if len(parts) > 1 else ""
        output_field = parts[2].strip() if len(parts) > 2 else "value"
        return _get_stub(
            value,
            stub_name,
            output_field,
            app_instance=app_instance,
            row=row,
        )

    # Fallback: try registry with no args
    try:
        fn = _registry.get(transform)
        if fn is not None:
            return fn(value, app_instance=app_instance, row=row)
    except Exception:
        pass

    return str(value)
