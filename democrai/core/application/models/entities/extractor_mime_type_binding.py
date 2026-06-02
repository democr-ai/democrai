from __future__ import annotations

from typing import Any

from democrai.core.application.models.base import BaseCoreModel
from democrai.core.infrastructure.database import SessionLocal
from democrai.core.infrastructure.database.models import ExtractorMimeTypeBinding


class ExtractorMimeTypeBindingCoreModel(BaseCoreModel):
    name = "extractor_mime_type_binding"
    sqlalchemy_model = ExtractorMimeTypeBinding

    def serialize_row(self, item: ExtractorMimeTypeBinding) -> dict[str, Any]:
        return {
            "id": item.id,
            "mime_type": item.mime_type,
            "extractor_id": item.extractor_id,
        }

    def filters_model(self) -> list[dict[str, Any]]:
        return [
            {"field": "id", "type": "int"},
            {"field": "mime_type", "type": "text"},
            {"field": "extractor_id", "type": "text"},
        ]

    def table_model(self) -> list[dict[str, Any]]:
        return [
            {"field": "id", "type": "int", "filterable": False},
            {"field": "mime_type", "type": "str", "filterable": True},
            {"field": "extractor_id", "type": "str", "filterable": True},
        ]

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        mime_type = str(payload.get("mime_type") or "").strip().lower()
        extractor_id = str(payload.get("extractor_id") or "").strip().lower()
        if not mime_type or not extractor_id:
            raise ValueError("mime_type and extractor_id are required")

        with SessionLocal() as session:
            existing = (
                session.query(ExtractorMimeTypeBinding)
                .filter(ExtractorMimeTypeBinding.mime_type == mime_type)
                .first()
            )
            if existing is not None:
                raise ValueError("mime_type binding already exists")
            row = ExtractorMimeTypeBinding(
                mime_type=mime_type,
                extractor_id=extractor_id,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return self.serialize_detail(row)

    def update(self, entity_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
        with SessionLocal() as session:
            row = self._apply_access_scope(self.base_query(session)).filter(
                ExtractorMimeTypeBinding.id == entity_id
            ).first()
            if row is None:
                return None

            if "mime_type" in payload:
                mime_type = str(payload.get("mime_type") or "").strip().lower()
                if not mime_type:
                    raise ValueError("mime_type is required")
                row.mime_type = mime_type

            if "extractor_id" in payload:
                extractor_id = str(payload.get("extractor_id") or "").strip().lower()
                if not extractor_id:
                    raise ValueError("extractor_id is required")
                row.extractor_id = extractor_id

            session.commit()
            session.refresh(row)
            return self.serialize_detail(row)

    def delete(self, entity_id: int) -> bool:
        with SessionLocal() as session:
            row = self._apply_access_scope(self.base_query(session)).filter(
                ExtractorMimeTypeBinding.id == entity_id
            ).first()
            if row is None:
                return False
            session.delete(row)
            session.commit()
            return True
