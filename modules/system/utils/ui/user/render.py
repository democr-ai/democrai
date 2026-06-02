from __future__ import annotations


def literal_string(value: str) -> dict:
    return {"literalString": str(value or "")}


def resolve_route_id(params: dict) -> int | None:
    route_params = params.get("route_params")
    if not isinstance(route_params, dict) or "id" not in route_params:
        return None
    return int(route_params["id"])


def set_title_text(title_component, text: str) -> None:
    if title_component is None:
        return
    title_component.set_prop("text", literal_string(text))
