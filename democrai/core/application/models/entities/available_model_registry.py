from __future__ import annotations

from typing import Any

from democrai.core.application.ai.constants import methods_for_capabilities, normalize_capabilities
from democrai.core.application.models.base import BaseCoreModel
from democrai.core.infrastructure.database import SessionLocal
from democrai.core.infrastructure.database.models import AvailableModelRegistry
from democrai.core.platform.utils.identity import to_optional_int


def _normalize_csv(raw_value: Any) -> str:
    if raw_value is None:
        return ""
    if isinstance(raw_value, str):
        parts = [part.strip() for part in raw_value.split(",")]
    elif isinstance(raw_value, list):
        parts = [str(part).strip() for part in raw_value]
    else:
        parts = [str(raw_value).strip()]
    return ",".join([part for part in parts if part])


def _normalize_capabilities_csv(raw_value: Any) -> str:
    return ",".join(normalize_capabilities(raw_value))


def _serialize_csv(raw_value: Any) -> list[str]:
    value = str(raw_value or "")
    return [part.strip() for part in value.split(",") if part.strip()]


def _serialize_capabilities(raw_value: Any) -> list[str]:
    return normalize_capabilities(raw_value)


class AvailableModelRegistryCoreModel(BaseCoreModel):
    name = "available_model_registry"
    sqlalchemy_model = AvailableModelRegistry

    def serialize_row(self, item: AvailableModelRegistry) -> dict[str, Any]:
        return {
            "id": item.id,
            "name": item.name,
            "label": item.label,
            "catalog_model_id": item.catalog_model_id,
            "source_kind": item.source_kind,
            "provider_hint": item.provider_hint,
            "format": item.format,
            "family": item.family,
            "summary": item.summary,
            "storage_ref": item.storage_ref,
            "remote_url": item.remote_url,
            "version": item.version,
            "capabilities": _serialize_capabilities(item.capabilities),
            "runtime_methods": methods_for_capabilities(item.capabilities),
            "extended_capabilities": _serialize_csv(item.extended_capabilities),
            "interfaces": _serialize_csv(item.interfaces),
            "tags": _serialize_csv(item.tags),
            "requirements": item.requirements,
            "artifacts": item.artifacts,
            "metadata": item.metadata_json,
            "source_payload": item.source_payload,
            "extra_config": item.extra_config,
            "status": item.status,
        }

    def filters_model(self) -> list[dict[str, Any]]:
        return [
            {"field": "id", "type": "int"},
            {"field": "name", "type": "text"},
            {"field": "label", "type": "text"},
            {"field": "catalog_model_id", "type": "text"},
            {"field": "source_kind", "type": "text"},
            {"field": "provider_hint", "type": "text"},
            {"field": "format", "type": "text"},
            {"field": "status", "type": "text"},
            {"field": "capabilities", "type": "text"},
        ]

    def table_model(self) -> list[dict[str, Any]]:
        return [
            {"field": "id", "type": "int", "filterable": False},
            {"field": "label", "type": "str", "filterable": True, "filter_type": "text"},
            {"field": "source_kind", "type": "str", "filterable": True, "filter_type": "text"},
            {"field": "format", "type": "str", "filterable": True, "filter_type": "text"},
            {"field": "status", "type": "str", "filterable": True, "filter_type": "text"},
            {"field": "capabilities", "type": "list", "filterable": True, "filter_type": "text"},
        ]

    def _apply_filters(self, query, filters: dict[str, Any]):
        for field_name in (
            "name",
            "label",
            "catalog_model_id",
            "source_kind",
            "provider_hint",
            "format",
            "status",
        ):
            value = filters.get(field_name)
            if isinstance(value, str):
                query = query.filter(
                    getattr(AvailableModelRegistry, field_name).ilike(f"%{value}%")
                )

        capabilities = filters.get("capabilities")
        if isinstance(capabilities, str):
            query = query.filter(
                AvailableModelRegistry.capabilities.ilike(f"%{capabilities}%")
            )

        entity_id = to_optional_int(filters.get("id"))
        if entity_id is not None:
            query = query.filter(AvailableModelRegistry.id == entity_id)

        return query

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = str(payload.get("name") or "").strip()
        label = str(payload.get("label") or name).strip()
        if not name or not label:
            raise ValueError("name and label are required")

        with SessionLocal() as session:
            existing = (
                session.query(AvailableModelRegistry)
                .filter(AvailableModelRegistry.name == name)
                .first()
            )
            if existing is not None:
                raise ValueError("available model name already in use")

            row = AvailableModelRegistry(
                name=name,
                label=label,
                catalog_model_id=str(payload.get("catalog_model_id") or "").strip() or None,
                source_kind=str(payload.get("source_kind") or "manual").strip() or "manual",
                provider_hint=str(payload.get("provider_hint") or "").strip() or None,
                format=str(payload.get("format") or "").strip() or None,
                family=str(payload.get("family") or "").strip() or None,
                summary=str(payload.get("summary") or "").strip() or None,
                storage_ref=str(payload.get("storage_ref") or "").strip() or None,
                remote_url=str(payload.get("remote_url") or "").strip() or None,
                version=str(payload.get("version") or "").strip() or None,
                capabilities=_normalize_capabilities_csv(payload.get("capabilities")) or None,
                extended_capabilities=_normalize_csv(payload.get("extended_capabilities")) or None,
                interfaces=_normalize_csv(payload.get("interfaces")) or None,
                tags=_normalize_csv(payload.get("tags")) or None,
                requirements=payload.get("requirements") if isinstance(payload.get("requirements"), dict) else None,
                artifacts=payload.get("artifacts") if isinstance(payload.get("artifacts"), list) else None,
                metadata_json=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else None,
                source_payload=payload.get("source_payload") if isinstance(payload.get("source_payload"), dict) else None,
                extra_config=payload.get("extra_config") if isinstance(payload.get("extra_config"), dict) else None,
                status=str(payload.get("status") or "available").strip() or "available",
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return self.serialize_detail(row)

    def update(self, entity_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
        with SessionLocal() as session:
            row = self._apply_access_scope(self.base_query(session)).filter(
                AvailableModelRegistry.id == entity_id
            ).first()
            if row is None:
                return None

            if "name" in payload:
                name = str(payload.get("name") or "").strip()
                if not name:
                    raise ValueError("name is required")
                duplicate = (
                    session.query(AvailableModelRegistry)
                    .filter(
                        AvailableModelRegistry.name == name,
                        AvailableModelRegistry.id != entity_id,
                    )
                    .first()
                )
                if duplicate is not None:
                    raise ValueError("available model name already in use")
                row.name = name

            for field_name in (
                "label",
                "catalog_model_id",
                "source_kind",
                "provider_hint",
                "format",
                "family",
                "summary",
                "storage_ref",
                "remote_url",
                "version",
                "status",
            ):
                if field_name in payload:
                    value = str(payload.get(field_name) or "").strip()
                    setattr(row, field_name, value or None)

            if "capabilities" in payload:
                row.capabilities = (
                    _normalize_capabilities_csv(payload.get("capabilities")) or None
                )
            if "extended_capabilities" in payload:
                row.extended_capabilities = (
                    _normalize_csv(payload.get("extended_capabilities")) or None
                )
            if "interfaces" in payload:
                row.interfaces = _normalize_csv(payload.get("interfaces")) or None
            if "tags" in payload:
                row.tags = _normalize_csv(payload.get("tags")) or None
            if "requirements" in payload:
                row.requirements = (
                    payload.get("requirements")
                    if isinstance(payload.get("requirements"), dict)
                    else None
                )
            if "artifacts" in payload:
                row.artifacts = (
                    payload.get("artifacts")
                    if isinstance(payload.get("artifacts"), list)
                    else None
                )
            if "metadata" in payload:
                row.metadata_json = (
                    payload.get("metadata")
                    if isinstance(payload.get("metadata"), dict)
                    else None
                )
            if "source_payload" in payload:
                row.source_payload = (
                    payload.get("source_payload")
                    if isinstance(payload.get("source_payload"), dict)
                    else None
                )
            if "extra_config" in payload:
                row.extra_config = (
                    payload.get("extra_config")
                    if isinstance(payload.get("extra_config"), dict)
                    else None
                )

            session.commit()
            session.refresh(row)
            return self.serialize_detail(row)

    def delete(self, entity_id: int) -> bool:
        with SessionLocal() as session:
            row = self._apply_access_scope(self.base_query(session)).filter(
                AvailableModelRegistry.id == entity_id
            ).first()
            if row is None:
                return False
            session.delete(row)
            session.commit()
            return True
