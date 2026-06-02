from __future__ import annotations

from types import SimpleNamespace

from clients.qtdesktop.ui.renderers.domains.data.cell_formatters import apply_transform


def test_get_stub_transform_resolves_value_from_global_store():
    store = SimpleNamespace(
        get=lambda key, default=None, scope="auto": (
            [
                {"key": 1, "value": "super"},
                {"key": 2, "value": "organization"},
                {"key": 3, "value": "user"},
            ]
            if key == "/stubs/access_levels"
            else default
        )
    )
    app = SimpleNamespace(store=store)

    assert (
        apply_transform(2, "get_stub:access_levels", app_instance=app)
        == "organization"
    )
    assert apply_transform(99, "get_stub:access_levels", app_instance=app) == "99"

