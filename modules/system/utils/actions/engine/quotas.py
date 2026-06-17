from __future__ import annotations

from typing import Any


GLOBAL_LIMIT_SCOPES = {"all", "guest"}
TARGET_SCOPES = {"organization", "role", "user"}


def quota_counter_table_model(module_sdk) -> list[dict[str, Any]]:
    return [
        {
            "field": "id",
            "type": "int",
            "header": module_sdk.i18n.t("system.engine.quotas.field.id"),
            "filterable": False,
        },
        {
            "field": "name",
            "type": "str",
            "header": module_sdk.i18n.t("system.engine.quotas.field.counter"),
        },
        {
            "field": "period_label",
            "type": "str",
            "header": module_sdk.i18n.t("system.engine.quotas.field.period"),
        },
    ]


def quota_limit_table_model(module_sdk) -> list[dict[str, Any]]:
    return [
        {
            "field": "engine_label",
            "type": "str",
            "header": module_sdk.i18n.t("system.engine.quotas.field.engine"),
        },
        {
            "field": "counter_label",
            "type": "str",
            "header": module_sdk.i18n.t("system.engine.quotas.field.counter"),
        },
        {
            "field": "period_label",
            "type": "str",
            "header": module_sdk.i18n.t("system.engine.quotas.field.period"),
        },
        {
            "field": "scope_label",
            "type": "str",
            "header": module_sdk.i18n.t("system.engine.quotas.field.scope"),
        },
        {
            "field": "metric_type_label",
            "type": "str",
            "header": module_sdk.i18n.t("system.engine.quotas.field.metric_type"),
        },
        {
            "field": "limit_value",
            "type": "int",
            "header": module_sdk.i18n.t("system.engine.quotas.field.limit_value"),
        },
    ]


def quota_counter_rows(
    module_sdk,
    *,
    rows: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    if rows is None:
        listing = module_sdk.engines.list_quota_counters(page=0, page_size=200)
        rows = list((listing or {}).get("rows") or [])
    return [
        {
            **row,
            "period_label": period_label(
                module_sdk,
                row.get("period_count"),
                row.get("period_unit"),
            ),
            "update_path": f"/system/engine_quota/counters/{int(row['id'])}/update",
        }
        for row in rows
        if isinstance(row, dict) and row.get("id") is not None
    ]


def quota_limit_rows(
    module_sdk,
    *,
    rows: list[dict[str, Any]],
    subject_scope: str,
    subject_id: int,
) -> list[dict[str, Any]]:
    counters = _rows_by_id(
        (module_sdk.engines.list_quota_counters(page=0, page_size=200) or {}).get("rows")
    )
    engines = _rows_by_id(
        (module_sdk.models.engine_registry.all(sort={"field": "name", "direction": "asc"}) or {}).get("rows")
    )
    result: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict) or row.get("id") is None:
            continue
        counter = counters.get(int(row.get("counter_id") or 0), {})
        engine = engines.get(int(row.get("engine_row_id") or 0), {})
        result.append(
            {
                **row,
                "subject_scope": subject_scope,
                "subject_id": int(subject_id),
                "engine_label": engine_label(engine),
                "counter_label": str(counter.get("name") or row.get("counter_id") or ""),
                "period_label": period_label(
                    module_sdk,
                    counter.get("period_count"),
                    counter.get("period_unit"),
                ),
                "metric_type_label": metric_type_label(module_sdk, row.get("metric_type")),
                "scope_label": scope_label(module_sdk, row.get("scope_type")),
                "update_path": (
                    "/system/engine_quota/limit/"
                    f"{subject_scope}/{int(subject_id)}/{int(row['id'])}/update"
                ),
            }
        )
    return result


def counter_form_model(
    module_sdk,
    *,
    defaults: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    values = dict(defaults or {})
    period_options = [
        {
            "label": period_unit_label(module_sdk, unit),
            "value": unit,
        }
        for unit in module_sdk.engines.quota_metadata().get("period_units", [])
    ]
    return [
        {
            "name": "name",
            "type": "text",
            "label": module_sdk.i18n.t("system.engine.quotas.field.counter"),
            "value": str(values.get("name") or ""),
            "validations": [
                {
                    "rule": "required",
                    "message": module_sdk.i18n.t("system.engine.quotas.validation.counter_required"),
                }
            ],
        },
        {
            "name": "period_count",
            "type": "integer",
            "label": module_sdk.i18n.t("system.engine.quotas.field.period_count"),
            "value": int(values.get("period_count") or 1),
            "validations": [
                {
                    "rule": "min",
                    "params": [1],
                    "message": module_sdk.i18n.t("system.engine.quotas.validation.period_count_min"),
                }
            ],
        },
        {
            "name": "period_unit",
            "type": "select",
            "label": module_sdk.i18n.t("system.engine.quotas.field.period"),
            "value": str(values.get("period_unit") or "day"),
            "options": period_options,
            "validations": [
                {
                    "rule": "required",
                    "message": module_sdk.i18n.t("system.engine.quotas.validation.period_required"),
                }
            ],
        },
    ]


def limit_form_model(
    module_sdk,
    *,
    scope: str,
    defaults: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    values = dict(defaults or {})
    metric_options = [
        {
            "label": metric_type_label(module_sdk, metric),
            "value": metric,
        }
        for metric in module_sdk.engines.quota_metadata().get("metric_types", [])
    ]
    fields: list[dict[str, Any]] = []
    if scope in TARGET_SCOPES:
        fields.append(
            {
                "name": "engine_row_id",
                "type": "select",
                "label": module_sdk.i18n.t("system.engine.quotas.field.engine"),
                "value": values.get("engine_row_id"),
                "options": engine_options(module_sdk),
                "validations": [
                    {
                        "rule": "required",
                        "message": module_sdk.i18n.t("system.engine.quotas.validation.engine_required"),
                    }
                ],
            }
        )
    if scope == "global":
        fields.append(
            {
                "name": "scope_type",
                "type": "select",
                "label": module_sdk.i18n.t("system.engine.quotas.field.scope"),
                "value": str(values.get("scope_type") or "all"),
                "options": [
                    {"label": scope_label(module_sdk, "all"), "value": "all"},
                    {"label": scope_label(module_sdk, "guest"), "value": "guest"},
                ],
                "validations": [
                    {
                        "rule": "required",
                        "message": module_sdk.i18n.t("system.engine.quotas.validation.scope_required"),
                    }
                ],
            }
        )
    fields.extend(
        [
            {
                "name": "counter_id",
                "type": "select",
                "label": module_sdk.i18n.t("system.engine.quotas.field.counter"),
                "value": values.get("counter_id"),
                "options": counter_options(module_sdk),
                "validations": [
                    {
                        "rule": "required",
                        "message": module_sdk.i18n.t("system.engine.quotas.validation.counter_required"),
                    }
                ],
            },
            {
                "name": "metric_type",
                "type": "select",
                "label": module_sdk.i18n.t("system.engine.quotas.field.metric_type"),
                "value": str(values.get("metric_type") or "total_tokens"),
                "options": metric_options,
                "validations": [
                    {
                        "rule": "required",
                        "message": module_sdk.i18n.t("system.engine.quotas.validation.metric_required"),
                    }
                ],
            },
            {
                "name": "limit_value",
                "type": "integer",
                "label": module_sdk.i18n.t("system.engine.quotas.field.limit_value"),
                "value": int(values.get("limit_value") or 0),
                "validations": [
                    {
                        "rule": "min",
                        "params": [0],
                        "message": module_sdk.i18n.t("system.engine.quotas.validation.limit_min"),
                    }
                ],
            },
        ]
    )
    return fields


def counter_options(module_sdk) -> list[dict[str, Any]]:
    rows = (module_sdk.engines.list_quota_counters(page=0, page_size=200) or {}).get("rows") or []
    return [
        {"label": str(row.get("name") or row.get("id")), "value": int(row["id"])}
        for row in rows
        if isinstance(row, dict) and row.get("id") is not None
    ]


def engine_options(module_sdk) -> list[dict[str, Any]]:
    rows = (module_sdk.models.engine_registry.all(sort={"field": "name", "direction": "asc"}) or {}).get("rows") or []
    return [
        {"label": engine_label(row), "value": int(row["id"])}
        for row in rows
        if isinstance(row, dict) and row.get("id") is not None
    ]


def engine_label(row: dict[str, Any]) -> str:
    name = str(row.get("name") or "").strip()
    provider = str(row.get("provider") or "").strip()
    if name and provider:
        return f"{name} ({provider})"
    return name or provider or str(row.get("id") or "")


def period_unit_label(module_sdk, value: Any) -> str:
    normalized = str(value or "").strip()
    key = f"system.engine.quotas.period.{normalized}"
    translated = module_sdk.i18n.t(key)
    return normalized if translated == key else translated


def period_label(module_sdk, count: Any, unit: Any) -> str:
    period_count = int(count or 1)
    return f"{period_count} {period_unit_label(module_sdk, unit)}"


def metric_type_label(module_sdk, value: Any) -> str:
    normalized = str(value or "").strip()
    key = f"system.engine.quotas.metric.{normalized}"
    translated = module_sdk.i18n.t(key)
    return normalized if translated == key else translated


def scope_label(module_sdk, value: Any) -> str:
    normalized = str(value or "").strip()
    key = f"system.engine.quotas.scope.{normalized}"
    translated = module_sdk.i18n.t(key)
    return normalized if translated == key else translated


def _rows_by_id(rows: Any) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    for row in rows or []:
        if not isinstance(row, dict) or row.get("id") is None:
            continue
        result[int(row["id"])] = row
    return result
