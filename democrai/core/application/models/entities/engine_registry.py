from __future__ import annotations

import asyncio
from typing import Any

from democrai.core.application.ai.engine.config_crypto import decrypt_provider_config
from democrai.core.application.ai.engine.config_crypto import encrypt_provider_config
from democrai.core.application.ai.engine.config_crypto import encrypted_keys_for_provider
from democrai.core.application.ai.engine.config_crypto import is_encrypted_value
from democrai.core.application.models.base import BaseCoreModel
from democrai.core.infrastructure.database import SessionLocal
from democrai.core.infrastructure.database.models import EngineRegistry
from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.platform.utils.identity import to_optional_int
from democrai.core.platform.utils.normalize import normalize_bool


def _log_allowlist_refresh_event_failure(exc: BaseException) -> None:
    logger = app_ctx().logger
    if logger is not None:
        logger.error(
            f"[engine_registry] failed_to_emit_allowlist_refresh_event: {exc}",
            "sandbox",
        )


def _request_os_allowlist_refresh(
    *,
    reason: str,
    mode: str,
    engine_id: str | None = None,
) -> None:
    from democrai.core.infrastructure.sandbox.os.events import (
        emit_application_network_allowlist_refresh_event,
    )

    payload = {
        "reason": reason,
        "resource_type": "engine",
        "module_name": "democrai.core.engine_registry",
        "target": engine_id or "",
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

    task = loop.create_task(
        emit_application_network_allowlist_refresh_event(payload=payload)
    )

    def _done_callback(completed: asyncio.Task) -> None:
        try:
            completed.result()
        except Exception as exc:
            _log_allowlist_refresh_event_failure(exc)

    task.add_done_callback(_done_callback)


class EngineRegistryCoreModel(BaseCoreModel):
    name = "engine_registry"
    sqlalchemy_model = EngineRegistry

    @staticmethod
    def _provider_payload(value: Any) -> str:
        return str(value or "").strip().lower()

    def _config_for_output(self, provider: str, config: dict[str, Any] | None) -> dict[str, Any]:
        return decrypt_provider_config(self._provider_payload(provider), dict(config or {}))

    def _config_for_create(self, provider: str, config: dict[str, Any] | None) -> dict[str, Any]:
        return encrypt_provider_config(self._provider_payload(provider), dict(config or {}))

    def _config_for_update(
        self,
        *,
        provider: str,
        current_stored: dict[str, Any] | None,
        incoming: dict[str, Any] | None,
    ) -> dict[str, Any]:
        resolved_provider = self._provider_payload(provider)
        incoming_payload = dict(incoming or {})
        current_plain = decrypt_provider_config(resolved_provider, dict(current_stored or {}))

        merged = dict(incoming_payload)
        for key in encrypted_keys_for_provider(resolved_provider):
            if key not in incoming_payload:
                if key in current_plain:
                    merged[key] = current_plain.get(key)
                continue
            value = merged.get(key)
            if is_encrypted_value(value):
                merged[key] = self._config_for_output(resolved_provider, {key: value}).get(key)

        return encrypt_provider_config(resolved_provider, merged)

    def serialize_row(self, item: EngineRegistry) -> dict[str, Any]:
        return {
            "id": item.id,
            "name": item.name,
            "provider": item.provider,
            "config": self._config_for_output(item.provider, item.config),
            "status": item.status,
            "supported": item.supported,
        }

    def filters_model(self) -> list[dict[str, Any]]:
        return [
            {"field": "id", "type": "int"},
            {"field": "name", "type": "text"},
            {"field": "provider", "type": "text"},
            {"field": "status", "type": "text"},
            {"field": "supported", "type": "bool"},
        ]

    def table_model(self) -> list[dict[str, Any]]:
        return [
            {"field": "id", "type": "int", "filterable": False},
            {"field": "name", "type": "str", "filterable": True, "filter_type": "text"},
            {"field": "provider", "type": "str", "filterable": True, "filter_type": "text"},
            {"field": "status", "type": "str", "filterable": True, "filter_type": "text"},
            {
                "field": "supported",
                "type": "bool",
                "filterable": True,
                "filter_type": "select",
                "options": [True, False],
            },
        ]

    def _apply_filters(self, query, filters: dict[str, Any]):
        name = filters.get("name")
        if isinstance(name, str):
            query = query.filter(EngineRegistry.name.ilike(f"%{name}%"))

        provider = filters.get("provider")
        if isinstance(provider, str):
            query = query.filter(EngineRegistry.provider == provider.strip().lower())

        status = filters.get("status")
        if isinstance(status, str):
            query = query.filter(EngineRegistry.status.ilike(f"%{status}%"))

        entity_id = to_optional_int(filters.get("id"))
        if entity_id is not None:
            query = query.filter(EngineRegistry.id == entity_id)

        if "supported" in filters:
            query = query.filter(
                EngineRegistry.supported == normalize_bool(filters.get("supported"))
            )

        return query

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = str(payload.get("name") or "").strip()
        provider = self._provider_payload(payload.get("provider"))
        if not name or not provider:
            raise ValueError("name and provider are required")

        config = payload.get("config")
        if config is None:
            config = {}
        if not isinstance(config, dict):
            raise ValueError("config must be an object")

        status = str(payload.get("status") or "uninstalled").strip() or "uninstalled"
        supported = normalize_bool(payload.get("supported"), default=False)

        with SessionLocal() as session:
            existing = session.query(EngineRegistry).filter(EngineRegistry.name == name).first()
            if existing is not None:
                raise ValueError("engine name already in use")

            row = EngineRegistry(
                name=name,
                provider=provider,
                config=self._config_for_create(provider, config),
                status=status,
                supported=supported,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            result = self.serialize_detail(row)
        _request_os_allowlist_refresh(
            reason="engine_registry_created",
            mode="create",
            engine_id=result["provider"],
        )
        return result

    def update(self, entity_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
        with SessionLocal() as session:
            row = self._apply_access_scope(self.base_query(session)).filter(
                EngineRegistry.id == entity_id
            ).first()
            if row is None:
                return None
            refresh_required = False

            if "name" in payload:
                name = str(payload.get("name") or "").strip()
                if not name:
                    raise ValueError("name is required")
                duplicate = (
                    session.query(EngineRegistry)
                    .filter(EngineRegistry.name == name, EngineRegistry.id != entity_id)
                    .first()
                )
                if duplicate is not None:
                    raise ValueError("engine name already in use")
                row.name = name

            if "provider" in payload:
                provider = self._provider_payload(payload.get("provider"))
                if not provider:
                    raise ValueError("provider is required")
                current_provider = self._provider_payload(row.provider)
                if current_provider != provider:
                    refresh_required = True
                    if "config" not in payload:
                        current_plain_config = self._config_for_output(
                            current_provider,
                            dict(row.config or {}),
                        )
                        row.config = self._config_for_create(
                            provider,
                            current_plain_config,
                        )
                row.provider = provider

            if "config" in payload:
                config = payload.get("config")
                if config is None:
                    config = {}
                if not isinstance(config, dict):
                    raise ValueError("config must be an object")
                provider_for_config = self._provider_payload(
                    payload.get("provider") if "provider" in payload else row.provider
                )
                encrypted = self._config_for_update(
                    provider=provider_for_config,
                    current_stored=dict(row.config or {}),
                    incoming=config,
                )
                if dict(row.config or {}) != dict(encrypted):
                    refresh_required = True
                row.config = encrypted

            if "status" in payload:
                row.status = str(payload.get("status") or "").strip() or "uninstalled"

            if "supported" in payload:
                row.supported = normalize_bool(payload.get("supported"), default=False)

            session.commit()
            session.refresh(row)
            result = self.serialize_detail(row)
        if refresh_required:
            _request_os_allowlist_refresh(
                reason="engine_registry_updated",
                mode="update",
                engine_id=result["provider"],
            )
        return result

    def delete(self, entity_id: int) -> bool:
        with SessionLocal() as session:
            row = self._apply_access_scope(self.base_query(session)).filter(
                EngineRegistry.id == entity_id
            ).first()
            if row is None:
                return False
            provider = row.provider
            session.delete(row)
            session.commit()
        _request_os_allowlist_refresh(
            reason="engine_registry_deleted",
            mode="delete",
            engine_id=provider,
        )
        return True
