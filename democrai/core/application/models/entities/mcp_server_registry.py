from __future__ import annotations

import asyncio
from typing import Any

from democrai.core.application.models.base import BaseCoreModel
from democrai.core.infrastructure.database import SessionLocal
from democrai.core.infrastructure.database.models import McpServerRegistry
from democrai.core.platform.mcp.crypto import decrypt_config
from democrai.core.platform.mcp.crypto import encrypt_config
from democrai.core.platform.utils.identity import to_optional_int
from democrai.core.platform.utils.normalize import normalize_bool
from democrai.core.platform.utils.runtime_names import validate_runtime_name_segment
from democrai.core.runtime.foundation.app import app_ctx


_ALLOWED_TRANSPORTS = {"http", "direct"}


def _normalize_transport(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in _ALLOWED_TRANSPORTS:
        raise ValueError("transport must be one of: http, direct")
    return normalized


def _validate_name(value: Any) -> str:
    return validate_runtime_name_segment(value, kind="mcp server name")


def _normalize_endpoint_url(value: Any) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError("endpoint_url is required")
    return normalized


def _normalize_timeout_ms(value: Any) -> int:
    parsed = to_optional_int(value)
    if parsed is None:
        return 15000
    return max(1000, min(parsed, 300000))


def _normalize_config(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("config must be an object")
    return dict(value)


def _log_allowlist_refresh_event_failure(exc: BaseException) -> None:
    logger = app_ctx().logger
    if logger is not None:
        logger.error(
            f"[mcp_server_registry] failed_to_emit_allowlist_refresh_event: {exc}",
            "sandbox",
        )


def _request_os_allowlist_refresh(
    *,
    reason: str,
    mode: str,
    server_name: str | None = None,
) -> None:
    from democrai.core.infrastructure.sandbox.os.events import (
        emit_application_network_allowlist_refresh_event,
    )

    payload = {
        "reason": reason,
        "resource_type": "mcp_server",
        "module_name": "democrai.core.mcp_server_registry",
        "target": server_name or "",
        "mode": mode,
    }
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is None:
        try:
            asyncio.run(emit_application_network_allowlist_refresh_event(payload=payload))
        except Exception as exc:
            _log_allowlist_refresh_event_failure(exc)
        return

    task = loop.create_task(emit_application_network_allowlist_refresh_event(payload=payload))

    def _done_callback(completed: asyncio.Task) -> None:
        try:
            completed.result()
        except Exception as exc:
            _log_allowlist_refresh_event_failure(exc)

    task.add_done_callback(_done_callback)


def _invalidate_mcp_tool_cache(server_name: str | None) -> None:
    from democrai.core.platform.mcp.runtime import mcp_runtime

    mcp_runtime.invalidate_tool_cache(server_name=server_name)


class McpServerRegistryCoreModel(BaseCoreModel):
    name = "mcp_server_registry"
    sqlalchemy_model = McpServerRegistry

    def serialize_row(self, item: McpServerRegistry) -> dict[str, Any]:
        return {
            "id": item.id,
            "name": item.name,
            "transport": item.transport,
            "endpoint_url": item.endpoint_url,
            "config": decrypt_config(item.config_encrypted),
            "enabled": item.enabled,
            "timeout_ms": item.timeout_ms,
        }

    def filters_model(self) -> list[dict[str, Any]]:
        return [
            {"field": "id", "type": "int"},
            {"field": "name", "type": "text"},
            {"field": "transport", "type": "text"},
            {"field": "enabled", "type": "bool"},
        ]

    def table_model(self) -> list[dict[str, Any]]:
        return [
            {"field": "id", "type": "int", "filterable": False},
            {"field": "name", "type": "str", "filterable": True, "filter_type": "text"},
            {
                "field": "transport",
                "type": "str",
                "filterable": True,
                "filter_type": "select",
                "options": ["http", "direct"],
            },
            {
                "field": "enabled",
                "type": "bool",
                "filterable": True,
                "filter_type": "select",
                "options": [True, False],
            },
            {"field": "timeout_ms", "type": "int", "filterable": False},
        ]

    def form_model_create(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "name",
                "type": "text",
                "label": "name",
                "validations": [
                    {"rule": "required", "message": "name is required"},
                    {
                        "rule": "regex",
                        "pattern": "^[A-Za-z0-9-]+$",
                        "message": "name may contain only letters, digits, and hyphens",
                    },
                ],
            },
            {
                "name": "transport",
                "type": "select",
                "label": "transport",
                "value": "http",
                "options": [
                    {"label": "http", "value": "http"},
                    {"label": "direct", "value": "direct"},
                ],
                "validations": [{"rule": "required", "message": "transport is required"}],
            },
            {
                "name": "endpoint_url",
                "type": "text",
                "label": "endpoint url",
                "validations": [
                    {"rule": "required", "message": "endpoint url is required"}
                ],
            },
            {
                "name": "config",
                "type": "textarea",
                "label": "config",
                "value": "{}",
                "rows": 8,
            },
            {
                "name": "enabled",
                "type": "toggle",
                "label": "enabled",
                "value": True,
            },
            {
                "name": "timeout_ms",
                "type": "text",
                "label": "timeout ms",
                "value": "15000",
            },
        ]

    def form_model_update(self, entity_id: int) -> list[dict[str, Any]]:
        return self.form_model_create()

    def _apply_filters(self, query, filters: dict[str, Any]):
        entity_id = to_optional_int(filters.get("id"))
        if entity_id is not None:
            query = query.filter(McpServerRegistry.id == entity_id)

        name = filters.get("name")
        if isinstance(name, str):
            query = query.filter(McpServerRegistry.name.ilike(f"%{name}%"))

        transport = filters.get("transport")
        if isinstance(transport, str):
            query = query.filter(McpServerRegistry.transport.ilike(f"%{transport}%"))

        if "enabled" in filters:
            query = query.filter(
                McpServerRegistry.enabled == normalize_bool(filters.get("enabled"))
            )

        return query

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = _validate_name(payload.get("name"))
        transport = _normalize_transport(payload.get("transport"))
        endpoint_url = _normalize_endpoint_url(payload.get("endpoint_url"))
        config = _normalize_config(payload.get("config"))
        enabled = normalize_bool(payload.get("enabled"), default=True)
        timeout_ms = _normalize_timeout_ms(payload.get("timeout_ms"))

        with SessionLocal() as session:
            existing = (
                session.query(McpServerRegistry)
                .filter(McpServerRegistry.name == name)
                .first()
            )
            if existing is not None:
                raise ValueError("mcp server name already in use")

            row = McpServerRegistry(
                name=name,
                transport=transport,
                endpoint_url=endpoint_url,
                config_encrypted=encrypt_config(config),
                enabled=enabled,
                timeout_ms=timeout_ms,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            result = self.serialize_detail(row)
        _request_os_allowlist_refresh(
            reason="mcp_server_registry_created",
            mode="create",
            server_name=result["name"],
        )
        _invalidate_mcp_tool_cache(result["name"])
        return result

    def update(self, entity_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
        with SessionLocal() as session:
            row = self._apply_access_scope(self.base_query(session)).filter(
                McpServerRegistry.id == entity_id
            ).first()
            if row is None:
                return None
            refresh_required = False
            previous_name = row.name

            if "name" in payload:
                name = _validate_name(payload.get("name"))
                duplicate = (
                    session.query(McpServerRegistry)
                    .filter(
                        McpServerRegistry.name == name,
                        McpServerRegistry.id != entity_id,
                    )
                    .first()
                )
                if duplicate is not None:
                    raise ValueError("mcp server name already in use")
                row.name = name

            if "transport" in payload:
                transport = _normalize_transport(payload.get("transport"))
                if row.transport != transport:
                    refresh_required = True
                row.transport = transport

            if "endpoint_url" in payload:
                endpoint_url = _normalize_endpoint_url(payload.get("endpoint_url"))
                if row.endpoint_url != endpoint_url:
                    refresh_required = True
                row.endpoint_url = endpoint_url

            if "config" in payload:
                config = _normalize_config(payload.get("config"))
                current_config = decrypt_config(row.config_encrypted)
                if current_config != config:
                    refresh_required = True
                row.config_encrypted = encrypt_config(config)

            if "enabled" in payload:
                enabled = normalize_bool(payload.get("enabled"), default=True)
                if row.enabled != enabled:
                    refresh_required = True
                row.enabled = enabled

            if "timeout_ms" in payload:
                row.timeout_ms = _normalize_timeout_ms(payload.get("timeout_ms"))

            session.commit()
            session.refresh(row)
            result = self.serialize_detail(row)

        new_name = result["name"]
        if refresh_required:
            _request_os_allowlist_refresh(
                reason="mcp_server_registry_updated",
                mode="update",
                server_name=new_name,
            )
        _invalidate_mcp_tool_cache(new_name)
        if previous_name and previous_name != new_name:
            _invalidate_mcp_tool_cache(previous_name)
        return result

    def delete(self, entity_id: int) -> bool:
        with SessionLocal() as session:
            row = self._apply_access_scope(self.base_query(session)).filter(
                McpServerRegistry.id == entity_id
            ).first()
            if row is None:
                return False
            name = row.name
            session.delete(row)
            session.commit()
        _request_os_allowlist_refresh(
            reason="mcp_server_registry_deleted",
            mode="delete",
            server_name=name,
        )
        _invalidate_mcp_tool_cache(name)
        return True
