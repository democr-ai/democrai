from __future__ import annotations

from clients.qtdesktop.ui.renderers.domains.data.descriptions import (
    _format_value,
    _normalize_model,
    _resolve_dynamic_value,
)


def test_descriptions_renderer_format_value_handles_types_and_formats():
    assert _format_value(True, {"field": "active", "type": "bool"}) == "Yes"
    assert _format_value(12.345, {"field": "amount", "type": "float", "format": ".2f"}) == "12.35"
    assert _format_value("2026-03-21T14:55:00", {"field": "updated", "type": "date", "format": "%d/%m/%Y"}) == "21/03/2026"
    assert _format_value("pipeline ok", {"field": "status", "type": "str", "transform": "upper"}) == "PIPELINE OK"


def test_descriptions_renderer_format_value_uses_placeholder_for_missing_data():
    assert _format_value(None, {"field": "notes", "placeholder": "N/A"}) == "N/A"
    assert _format_value(None, {"field": "notes"}) == "-"


def test_descriptions_renderer_normalize_model_falls_back_to_data_keys():
    model = _normalize_model([], {"order_id": "42", "total": 19.0})
    assert [item["field"] for item in model] == ["order_id", "total"]
    assert model[0]["label"] == "Order Id"


def test_descriptions_renderer_resolves_dynamic_values_from_bindings():
    class _Bindings:
        def resolve_value(self, value):
            if isinstance(value, dict) and value.get("type") == "store":
                return "from_store"
            if value == "$state.user.name":
                return "from_string_binding"
            return value

    app = type("_App", (), {"bindings": _Bindings()})()
    assert _resolve_dynamic_value({"type": "store", "path": "/user/name"}, app) == "from_store"
    assert _resolve_dynamic_value("$state.user.name", app) == "from_string_binding"
    assert _resolve_dynamic_value({"literalString": "static"}, app) == "static"


def test_descriptions_renderer_format_value_supports_get_stub_transform():
    class _Store:
        def get(self, key, default=None, scope="auto"):
            if key == "/stubs/access_levels":
                return [
                    {"key": 1, "value": "super"},
                    {"key": 2, "value": "organization"},
                    {"key": 3, "value": "user"},
                ]
            return default

    app = type("_App", (), {"store": _Store()})()
    assert (
        _format_value(
            2,
            {"field": "access_level", "type": "int", "transform": "get_stub:access_levels"},
            app_instance=app,
            row={"access_level": 2},
        )
        == "organization"
    )
