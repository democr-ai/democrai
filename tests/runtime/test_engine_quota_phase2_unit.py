from __future__ import annotations

import asyncio
import importlib
from types import SimpleNamespace

from democrai.sdk.engines import Engines
from modules.system.actions.engine import quotas as quota_actions
from modules.system.utils.actions.engine import quotas as quota_helpers


class _Model:
    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.created = []
        self.updated = []
        self.deleted = []

    def list(self, **kwargs):
        return {
            "rows": list(self.rows),
            "total_rows": len(self.rows),
            "page": kwargs.get("page", 0),
            "page_size": kwargs.get("page_size", 200),
        }

    def all(self, **kwargs):
        filters = dict(kwargs.get("filters") or {})
        rows = list(self.rows)
        for key, value in filters.items():
            rows = [row for row in rows if row.get(key) == value]
        return {"rows": rows}

    def view(self, row_id):
        return next((row for row in self.rows if row.get("id") == row_id), None)

    def create(self, payload):
        self.created.append(dict(payload))
        return {"id": 100, **payload}

    def update(self, row_id, payload):
        self.updated.append((row_id, dict(payload)))
        return {"id": row_id, **payload}

    def delete(self, row_id):
        self.deleted.append(row_id)
        return True


def _engines():
    limits = _Model(
        [
            {
                "id": 1,
                "counter_id": 10,
                "engine_row_id": 7,
                "scope_type": "all",
                "scope_id": None,
                "metric_type": "total_tokens",
                "limit_value": 100,
            },
            {
                "id": 2,
                "counter_id": 10,
                "engine_row_id": 7,
                "scope_type": "organization",
                "scope_id": 22,
                "metric_type": "requests",
                "limit_value": 200,
            },
        ]
    )
    counters = _Model([{"id": 10, "name": "daily", "period_count": 2, "period_unit": "day"}])
    sdk = SimpleNamespace(
        models=SimpleNamespace(
            engine_quota_limits=limits,
            engine_quota_counters=counters,
        )
    )
    return Engines(sdk), counters, limits


def test_engine_quota_sdk_scoped_methods_inject_scope_and_subject():
    engines, _counters, limits = _engines()

    listing = engines.list_organization_engine_quota_limits(organization_id=22)
    assert [row["id"] for row in listing["rows"]] == [2]

    engines.create_organization_engine_quota_limit(
        organization_id=22,
        payload={
            "engine_row_id": 7,
            "counter_id": 10,
            "metric_type": "requests",
            "limit_value": 50,
        },
    )
    assert limits.created[-1]["scope_type"] == "organization"
    assert limits.created[-1]["scope_id"] == 22
    assert limits.created[-1]["metric_type"] == "requests"

    engines.update_organization_engine_quota_limit(
        organization_id=22,
        limit_id=2,
        payload={"limit_value": 75},
    )
    assert limits.updated[-1] == (
        2,
        {"limit_value": 75, "scope_type": "organization", "scope_id": 22},
    )


def test_engine_quota_sdk_global_methods_restrict_scope():
    engines, _counters, limits = _engines()

    listing = engines.list_engine_global_quota_limits(engine_registry_id=7)
    assert [row["scope_type"] for row in listing["rows"]] == ["all"]

    engines.create_engine_global_quota_limit(
        engine_registry_id=7,
        payload={
            "counter_id": 10,
            "scope_type": "guest",
            "metric_type": "total_tokens",
            "limit_value": 30,
        },
    )
    assert limits.created[-1]["engine_row_id"] == 7
    assert limits.created[-1]["scope_type"] == "guest"
    assert limits.created[-1]["scope_id"] is None


def test_engine_quota_limit_form_does_not_expose_target_scope_selector():
    engines, _counters, _limits = _engines()
    module_sdk = SimpleNamespace(
        engines=engines,
        models=SimpleNamespace(
            engine_registry=_Model([{"id": 7, "name": "main", "provider": "local"}])
        ),
        i18n=SimpleNamespace(t=lambda key, context=None: key),
    )

    organization_form = quota_helpers.limit_form_model(
        module_sdk,
        scope="organization",
    )
    assert {field["name"] for field in organization_form} == {
        "engine_row_id",
        "counter_id",
        "metric_type",
        "limit_value",
    }
    metric_field = next(field for field in organization_form if field["name"] == "metric_type")
    assert [option["value"] for option in metric_field["options"]] == [
        "requests",
        "total_tokens",
    ]

    global_form = quota_helpers.limit_form_model(module_sdk, scope="global")
    scope_field = next(field for field in global_form if field["name"] == "scope_type")
    assert [option["value"] for option in scope_field["options"]] == ["all", "guest"]


def test_engine_quota_action_dispatch_uses_scoped_sdk_method():
    calls = []
    module_sdk = SimpleNamespace(
        engines=SimpleNamespace(
            create_user_engine_quota_limit=lambda **kwargs: calls.append(kwargs),
        )
    )

    quota_actions._create_limit(
        module_sdk,
        {
            "scope": "user",
            "subject_id": 5,
            "engine_quota_limit_form": {
                "engine_row_id": 7,
                "counter_id": 10,
                "metric_type": "requests",
                "limit_value": 20,
            },
        },
    )

    assert calls == [
        {
            "user_id": 5,
            "payload": {
                "engine_row_id": 7,
                "counter_id": 10,
                "metric_type": "requests",
                "limit_value": 20,
            },
        }
    ]


def test_engine_quota_actions_update_tables_without_full_render():
    effects = []

    class Effects:
        @staticmethod
        def notify(channel, payload):
            return {"notify": {"channel": channel, "payload": payload}}

        @staticmethod
        def ui_messages(messages):
            return {"ui_messages": messages}

        @staticmethod
        def respond(*items):
            return {"effects": list(items)}

        @staticmethod
        def render():
            raise AssertionError("quota actions must not trigger full page render")

    module_sdk = SimpleNamespace(
        effects=Effects(),
        i18n=SimpleNamespace(t=lambda key, context=None: key),
    )

    response = quota_actions._success(
        module_sdk,
        "title",
        "text",
        {"ui_property_update": {"id": "engine_quota_counters_table"}},
    )
    effects.extend(response["effects"])

    assert any("ui_property_update" in item for item in effects)
    assert not any("render" in item for item in effects)


def test_engine_quota_remote_limit_payload_uses_scope_context():
    engines, _counters, _limits = _engines()
    module_sdk = SimpleNamespace(
        engines=engines,
        models=SimpleNamespace(
            engine_registry=_Model([{"id": 7, "name": "main", "provider": "local"}])
        ),
        i18n=SimpleNamespace(t=lambda key, context=None: key),
    )

    payload = quota_actions._limit_table_payload(
        module_sdk,
        {"scope": "organization", "subject_id": 22, "page": 0, "pageSize": 25},
    )

    assert payload["total_rows"] == 1
    assert payload["rows"][0]["subject_scope"] == "organization"
    assert payload["rows"][0]["subject_id"] == 22
    assert payload["rows"][0]["metric_type_label"] == "requests"
    assert payload["rows"][0]["period_label"] == "2 day"


def test_engine_quota_counter_link_is_in_system_internal_menu(monkeypatch):
    system_module = importlib.import_module("modules.system")
    sidebar_entries = system_module.init({})["sidebar_entries"]
    assert [entry["id"] for entry in sidebar_entries] == ["system"]

    layout_mod = importlib.import_module("modules.system.ui.layout")
    captured = {}

    class UI:
        @staticmethod
        def prepare_shell_surface(*_args, **_kwargs):
            return "system_preview"

        @staticmethod
        def nav_active_path_rule(path, active_path=None):
            return {"path": path, "active_path": active_path}

        @staticmethod
        def TreeView(component_id, *, nodes, **kwargs):
            captured["tree_id"] = component_id
            captured["nodes"] = nodes
            captured["kwargs"] = kwargs

            class Tree:
                def set_property(self, *_args):
                    return None

            return Tree()

        @staticmethod
        def mount_shell_frame(*_args, **_kwargs):
            return "module_root"

    class Builder:
        def add(self, _component):
            return None

    monkeypatch.setattr(layout_mod, "sdk", SimpleNamespace(ui=UI()))
    asyncio.run(layout_mod.shell_layout(Builder()))

    ai_group = next(node for node in captured["nodes"] if node["id"] == "group_ai")
    quota_node = next(
        item for item in ai_group["children"] if item["id"] == "engine_quota_counters"
    )
    assert quota_node["path"] == "/system/engine_quota/counters/list"
    assert quota_node["active"]["active_path"] == "/system/engine_quota/counters"
