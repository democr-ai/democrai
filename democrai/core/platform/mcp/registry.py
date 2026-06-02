from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.exc import OperationalError

from democrai.core.infrastructure.database import SessionLocal
from democrai.core.infrastructure.database.models import McpServerRegistry
from democrai.core.infrastructure.database.models import OrganizationMcp
from democrai.core.platform.utils.identity import to_optional_int
from democrai.core.runtime.foundation.app import req_ctx
from .crypto import decrypt_config


_ALLOWED_TRANSPORTS = {"http", "direct"}


@dataclass(frozen=True)
class McpServerRecord:
    id: int
    name: str
    transport: str
    endpoint_url: str
    config: dict[str, Any]
    enabled: bool
    timeout_ms: int


def _normalize_transport(value: Any) -> str:
    return value.strip().lower() if isinstance(value, str) else ""


def _row_to_record(row: McpServerRegistry) -> McpServerRecord:
    transport = _normalize_transport(getattr(row, "transport", ""))
    if transport not in _ALLOWED_TRANSPORTS:
        raise ValueError(f"invalid_mcp_transport:{transport}")
    endpoint_value = getattr(row, "endpoint_url", "")
    endpoint_url = endpoint_value.strip() if isinstance(endpoint_value, str) else ""
    if not endpoint_url:
        raise ValueError("invalid_mcp_endpoint_url")
    raw_timeout_ms = getattr(row, "timeout_ms", 15000)
    timeout_ms = 15000 if raw_timeout_ms is None else int(raw_timeout_ms)
    name_value = getattr(row, "name", "")
    name = name_value.strip() if isinstance(name_value, str) else ""
    return McpServerRecord(
        id=int(getattr(row, "id")),
        name=name,
        transport=transport,
        endpoint_url=endpoint_url,
        config=decrypt_config(getattr(row, "config_encrypted", "")),
        enabled=bool(getattr(row, "enabled", False)),
        timeout_ms=max(1000, timeout_ms),
    )


def _current_organization_id() -> int | None:
    try:
        return to_optional_int(req_ctx().organization_id)
    except LookupError:
        return None


def list_servers(*, enabled_only: bool = True) -> list[McpServerRecord]:
    organization_id = _current_organization_id()
    try:
        with SessionLocal() as session:
            query = session.query(McpServerRegistry)
            if enabled_only:
                query = query.filter(McpServerRegistry.enabled.is_(True))
            if organization_id is not None:
                query = query.join(
                    OrganizationMcp,
                    OrganizationMcp.mcp_server_id == McpServerRegistry.id,
                ).filter(OrganizationMcp.organization_id == organization_id)
            rows = query.order_by(McpServerRegistry.name.asc()).all()
    except OperationalError:
        return []
    records: list[McpServerRecord] = []
    for row in rows:
        records.append(_row_to_record(row))
    return records


def get_server_by_name(name: str) -> McpServerRecord | None:
    normalized = name.strip() if isinstance(name, str) else ""
    if not normalized:
        return None
    organization_id = _current_organization_id()
    try:
        with SessionLocal() as session:
            query = session.query(McpServerRegistry).filter(
                McpServerRegistry.name == normalized,
                McpServerRegistry.enabled.is_(True),
            )
            if organization_id is not None:
                query = query.join(
                    OrganizationMcp,
                    OrganizationMcp.mcp_server_id == McpServerRegistry.id,
                ).filter(OrganizationMcp.organization_id == organization_id)
            row = query.first()
    except OperationalError:
        return None
    if row is None:
        return None
    return _row_to_record(row)
