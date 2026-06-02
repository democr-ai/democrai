from __future__ import annotations

from typing import Any

from democrai.core.application.models.base import BaseCoreModel
from democrai.core.infrastructure.database import SessionLocal
from democrai.core.infrastructure.database.models import ExtractorRegistry
from democrai.core.platform.utils.identity import to_optional_int
from democrai.core.platform.utils.normalize import normalize_bool


class ExtractorRegistryCoreModel(BaseCoreModel):
    name = "extractor_registry"
    sqlalchemy_model = ExtractorRegistry

    def serialize_row(self, item: ExtractorRegistry) -> dict[str, Any]:
        return {
            "id": item.id,
            "name": item.name,
            "extractor_id": item.extractor_id,
            "config": item.config,
            "install_config": item.install_config,
            "file_extensions": item.file_extensions,
            "mime_types": item.mime_types,
            "priority": item.priority,
            "status": item.status,
            "supported": item.supported,
        }

    def filters_model(self) -> list[dict[str, Any]]:
        return [
            {"field": "id", "type": "int"},
            {"field": "name", "type": "text"},
            {"field": "extractor_id", "type": "text"},
            {"field": "status", "type": "text"},
            {"field": "supported", "type": "bool"},
        ]

    def table_model(self) -> list[dict[str, Any]]:
        return [
            {"field": "id", "type": "int", "filterable": False},
            {"field": "name", "type": "str", "filterable": True, "filter_type": "text"},
            {
                "field": "extractor_id",
                "type": "str",
                "filterable": True,
                "filter_type": "text",
            },
            {"field": "status", "type": "str", "filterable": True, "filter_type": "text"},
            {
                "field": "supported",
                "type": "bool",
                "filterable": True,
                "filter_type": "select",
                "options": [True, False],
            },
            {"field": "priority", "type": "int", "filterable": False},
        ]

    def _apply_filters(self, query, filters: dict[str, Any]):
        name = filters.get("name")
        if isinstance(name, str):
            query = query.filter(ExtractorRegistry.name.ilike(f"%{name}%"))

        extractor_id = filters.get("extractor_id")
        if isinstance(extractor_id, str):
            query = query.filter(
                ExtractorRegistry.extractor_id.ilike(f"%{extractor_id}%")
            )

        status = filters.get("status")
        if isinstance(status, str):
            query = query.filter(ExtractorRegistry.status.ilike(f"%{status}%"))

        entity_id = to_optional_int(filters.get("id"))
        if entity_id is not None:
            query = query.filter(ExtractorRegistry.id == entity_id)

        if "supported" in filters:
            query = query.filter(
                ExtractorRegistry.supported == normalize_bool(filters.get("supported"))
            )

        return query

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = str(payload.get("name") or "").strip()
        extractor_id = str(payload.get("extractor_id") or "").strip()
        if not name or not extractor_id:
            raise ValueError("name and extractor_id are required")

        config = payload.get("config")
        if config is None:
            config = {}
        if not isinstance(config, dict):
            raise ValueError("config must be an object")

        install_config = payload.get("install_config")
        if install_config is None:
            install_config = {}
        if not isinstance(install_config, dict):
            raise ValueError("install_config must be an object")

        file_extensions = payload.get("file_extensions")
        if file_extensions is None:
            file_extensions = []
        if not isinstance(file_extensions, list):
            raise ValueError("file_extensions must be a list")

        mime_types = payload.get("mime_types")
        if mime_types is None:
            mime_types = []
        if not isinstance(mime_types, list):
            raise ValueError("mime_types must be a list")

        priority = int(payload.get("priority") or 0)
        status = str(payload.get("status") or "uninstalled").strip() or "uninstalled"
        supported = normalize_bool(payload.get("supported"), default=False)

        with SessionLocal() as session:
            existing = session.query(ExtractorRegistry).filter(
                ExtractorRegistry.name == name
            ).first()
            if existing is not None:
                raise ValueError("extractor name already in use")

            row = ExtractorRegistry(
                name=name,
                extractor_id=extractor_id,
                config=config,
                install_config=install_config,
                file_extensions=list(file_extensions),
                mime_types=list(mime_types),
                priority=priority,
                status=status,
                supported=supported,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return self.serialize_detail(row)

    def update(self, entity_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
        with SessionLocal() as session:
            row = self._apply_access_scope(self.base_query(session)).filter(
                ExtractorRegistry.id == entity_id
            ).first()
            if row is None:
                return None

            if "name" in payload:
                name = str(payload.get("name") or "").strip()
                if not name:
                    raise ValueError("name is required")
                duplicate = (
                    session.query(ExtractorRegistry)
                    .filter(
                        ExtractorRegistry.name == name,
                        ExtractorRegistry.id != entity_id,
                    )
                    .first()
                )
                if duplicate is not None:
                    raise ValueError("extractor name already in use")
                row.name = name

            if "extractor_id" in payload:
                extractor_id = str(payload.get("extractor_id") or "").strip()
                if not extractor_id:
                    raise ValueError("extractor_id is required")
                row.extractor_id = extractor_id

            if "config" in payload:
                config = payload.get("config")
                if config is None:
                    config = {}
                if not isinstance(config, dict):
                    raise ValueError("config must be an object")
                row.config = config

            if "install_config" in payload:
                install_config = payload.get("install_config")
                if install_config is None:
                    install_config = {}
                if not isinstance(install_config, dict):
                    raise ValueError("install_config must be an object")
                row.install_config = install_config

            if "file_extensions" in payload:
                file_extensions = payload.get("file_extensions")
                if not isinstance(file_extensions, list):
                    raise ValueError("file_extensions must be a list")
                row.file_extensions = list(file_extensions)

            if "mime_types" in payload:
                mime_types = payload.get("mime_types")
                if not isinstance(mime_types, list):
                    raise ValueError("mime_types must be a list")
                row.mime_types = list(mime_types)

            if "priority" in payload:
                row.priority = int(payload.get("priority") or 0)

            if "status" in payload:
                row.status = str(payload.get("status") or "").strip() or "uninstalled"

            if "supported" in payload:
                row.supported = normalize_bool(payload.get("supported"), default=False)

            session.commit()
            session.refresh(row)
            return self.serialize_detail(row)

    def delete(self, entity_id: int) -> bool:
        with SessionLocal() as session:
            row = self._apply_access_scope(self.base_query(session)).filter(
                ExtractorRegistry.id == entity_id
            ).first()
            if row is None:
                return False
            session.delete(row)
            session.commit()
            return True
