from __future__ import annotations

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
                "limit_total_tokens": 100,
            },
            {
                "id": 2,
                "counter_id": 10,
                "engine_row_id": 7,
                "scope_type": "organization",
                "scope_id": 22,
                "limit_total_tokens": 200,
            },
        ]
    )
    counters = _Model([{"id": 10, "name": "daily", "period_unit": "day"}])
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
        payload={"engine_row_id": 7, "counter_id": 10, "limit_total_tokens": 50},
    )
    assert limits.created[-1]["scope_type"] == "organization"
    assert limits.created[-1]["scope_id"] == 22

    engines.update_organization_engine_quota_limit(
        organization_id=22,
        limit_id=2,
        payload={"limit_total_tokens": 75},
    )
    assert limits.updated[-1] == (
        2,
        {"limit_total_tokens": 75, "scope_type": "organization", "scope_id": 22},
    )


def test_engine_quota_sdk_global_methods_restrict_scope():
    engines, _counters, limits = _engines()

    listing = engines.list_engine_global_quota_limits(engine_registry_id=7)
    assert [row["scope_type"] for row in listing["rows"]] == ["all"]

    engines.create_engine_global_quota_limit(
        engine_registry_id=7,
        payload={"counter_id": 10, "scope_type": "guest", "limit_total_tokens": 30},
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
        "limit_total_tokens",
    }

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
                "limit_total_tokens": 20,
            },
        },
    )

    assert calls == [
        {
            "user_id": 5,
            "payload": {
                "engine_row_id": 7,
                "counter_id": 10,
                "limit_total_tokens": 20,
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
