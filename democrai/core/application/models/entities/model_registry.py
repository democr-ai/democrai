from __future__ import annotations

from typing import Any

from democrai.core.application.ai.constants import methods_for_capabilities, normalize_capabilities
from democrai.core.application.models.base import BaseCoreModel
from democrai.core.infrastructure.database import SessionLocal
from democrai.core.infrastructure.database.models import (
    AvailableModelRegistry,
    EngineRegistry,
    ModelRegistry,
)
from democrai.core.platform.utils.identity import to_optional_int


def _normalize_capabilities(raw_value: Any) -> str:
    return ",".join(normalize_capabilities(raw_value))


def _serialize_capabilities(raw_value: Any) -> list[str]:
    return normalize_capabilities(raw_value)


class ModelRegistryCoreModel(BaseCoreModel):
    name = "model_registry"
    sqlalchemy_model = ModelRegistry

    def serialize_row(self, item: ModelRegistry) -> dict[str, Any]:
        return {
            "id": item.id,
            "name": item.name,
            "engine_id": item.engine_id,
            "available_model_id": item.available_model_id,
            "model_path": item.model_path,
            "vram_required_mb": item.vram_required_mb,
            "ram_required_mb": item.ram_required_mb,
            "is_downloaded": item.is_downloaded,
            "remote_url": item.remote_url,
            "version": item.version,
            "capabilities": _serialize_capabilities(item.capabilities),
            "runtime_methods": methods_for_capabilities(item.capabilities),
            "extra_config": item.extra_config,
            "status": item.status,
        }

    def filters_model(self) -> list[dict[str, Any]]:
        return [
            {"field": "id", "type": "int"},
            {"field": "name", "type": "text"},
            {"field": "engine_id", "type": "int"},
            {"field": "available_model_id", "type": "int"},
            {"field": "status", "type": "text"},
            {"field": "is_downloaded", "type": "int"},
            {"field": "capabilities", "type": "text"},
        ]

    def table_model(self) -> list[dict[str, Any]]:
        return [
            {"field": "id", "type": "int", "filterable": False},
            {"field": "name", "type": "str", "filterable": True, "filter_type": "text"},
            {"field": "engine_id", "type": "int", "filterable": True, "filter_type": "int"},
            {
                "field": "available_model_id",
                "type": "int",
                "filterable": True,
                "filter_type": "int",
            },
            {"field": "status", "type": "str", "filterable": True, "filter_type": "text"},
            {
                "field": "is_downloaded",
                "type": "int",
                "filterable": True,
                "filter_type": "select",
                "options": [0, 1],
            },
            {"field": "capabilities", "type": "list", "filterable": True, "filter_type": "text"},
        ]

    def _apply_filters(self, query, filters: dict[str, Any]):
        name = filters.get("name")
        if isinstance(name, str):
            query = query.filter(ModelRegistry.name.ilike(f"%{name}%"))

        status = filters.get("status")
        if isinstance(status, str):
            query = query.filter(ModelRegistry.status.ilike(f"%{status}%"))

        capabilities = filters.get("capabilities")
        if isinstance(capabilities, str):
            query = query.filter(ModelRegistry.capabilities.ilike(f"%{capabilities}%"))

        for field_name in ("id", "engine_id", "available_model_id", "is_downloaded"):
            parsed = to_optional_int(filters.get(field_name))
            if parsed is None:
                continue
            query = query.filter(getattr(ModelRegistry, field_name) == parsed)

        return query

    def _ensure_engine_exists(self, session, engine_id: int) -> None:
        exists = session.query(EngineRegistry.id).filter(EngineRegistry.id == engine_id).first()
        if exists is None:
            raise ValueError("engine_id does not exist")

    def _ensure_available_model_exists(self, session, available_model_id: int) -> None:
        exists = (
            session.query(AvailableModelRegistry.id)
            .filter(AvailableModelRegistry.id == available_model_id)
            .first()
        )
        if exists is None:
            raise ValueError("available_model_id does not exist")

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = str(payload.get("name") or "").strip()
        engine_id = to_optional_int(payload.get("engine_id"))
        if not name or engine_id is None:
            raise ValueError("name and engine_id are required")
        available_model_id = to_optional_int(payload.get("available_model_id"))

        with SessionLocal() as session:
            existing = session.query(ModelRegistry).filter(ModelRegistry.name == name).first()
            if existing is not None:
                raise ValueError("model name already in use")
            self._ensure_engine_exists(session, engine_id)
            if available_model_id is not None:
                self._ensure_available_model_exists(session, available_model_id)

            extra_config = payload.get("extra_config")
            row = ModelRegistry(
                name=name,
                engine_id=engine_id,
                available_model_id=available_model_id,
                model_path=str(payload.get("model_path") or "").strip() or None,
                vram_required_mb=to_optional_int(payload.get("vram_required_mb")) or 0,
                ram_required_mb=to_optional_int(payload.get("ram_required_mb")) or 0,
                is_downloaded=1 if to_optional_int(payload.get("is_downloaded")) else 0,
                remote_url=str(payload.get("remote_url") or "").strip() or None,
                version=str(payload.get("version") or "").strip() or None,
                capabilities=_normalize_capabilities(payload.get("capabilities")) or None,
                extra_config=extra_config if isinstance(extra_config, dict) else None,
                status=str(payload.get("status") or "available").strip() or "available",
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            result = self.serialize_detail(row)
        return result

    def update(self, entity_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
        with SessionLocal() as session:
            row = self._apply_access_scope(self.base_query(session)).filter(
                ModelRegistry.id == entity_id
            ).first()
            if row is None:
                return None

            if "name" in payload:
                name = str(payload.get("name") or "").strip()
                if not name:
                    raise ValueError("name is required")
                duplicate = (
                    session.query(ModelRegistry)
                    .filter(ModelRegistry.name == name, ModelRegistry.id != entity_id)
                    .first()
                )
                if duplicate is not None:
                    raise ValueError("model name already in use")
                row.name = name

            if "engine_id" in payload:
                engine_id = to_optional_int(payload.get("engine_id"))
                if engine_id is None:
                    raise ValueError("engine_id is required")
                self._ensure_engine_exists(session, engine_id)
                row.engine_id = engine_id

            if "available_model_id" in payload:
                available_model_id = to_optional_int(payload.get("available_model_id"))
                if available_model_id is not None:
                    self._ensure_available_model_exists(session, available_model_id)
                row.available_model_id = available_model_id

            if "model_path" in payload:
                row.model_path = str(payload.get("model_path") or "").strip() or None
            if "vram_required_mb" in payload:
                row.vram_required_mb = to_optional_int(payload.get("vram_required_mb")) or 0
            if "ram_required_mb" in payload:
                row.ram_required_mb = to_optional_int(payload.get("ram_required_mb")) or 0
            if "is_downloaded" in payload:
                row.is_downloaded = 1 if to_optional_int(payload.get("is_downloaded")) else 0
            if "remote_url" in payload:
                row.remote_url = str(payload.get("remote_url") or "").strip() or None
            if "version" in payload:
                row.version = str(payload.get("version") or "").strip() or None
            if "capabilities" in payload:
                row.capabilities = _normalize_capabilities(payload.get("capabilities")) or None
            if "extra_config" in payload:
                extra_config = payload.get("extra_config")
                row.extra_config = extra_config if isinstance(extra_config, dict) else None
            if "status" in payload:
                row.status = str(payload.get("status") or "").strip() or "available"

            session.commit()
            session.refresh(row)
            result = self.serialize_detail(row)
        return result

    def delete(self, entity_id: int) -> bool:
        with SessionLocal() as session:
            row = self._apply_access_scope(self.base_query(session)).filter(
                ModelRegistry.id == entity_id
            ).first()
            if row is None:
                return False
            session.delete(row)
            session.commit()
        return True
