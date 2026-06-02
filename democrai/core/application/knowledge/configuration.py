"""Database-backed knowledge runtime configuration."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import joinedload

from democrai.core.application.ai.constants import AICapability, normalize_capabilities
from democrai.core.application.knowledge.records import KnowledgeItemRecord
from democrai.core.infrastructure.database import SessionLocal
from democrai.core.infrastructure.database.models import EngineRegistry
from democrai.core.infrastructure.database.models import KnowledgeRuntimeConfig
from democrai.core.infrastructure.database.models import ModelRegistry
from democrai.core.platform.utils.identity import to_optional_int
from democrai.core.platform.utils.normalize import normalize_bool


CONFIG_ROW_ID = 1


def _model_label(row: ModelRegistry) -> str:
    available_model = row.available_model
    model_name = (
        available_model.label if available_model is not None else None
    ) or row.name or str(row.id)
    engine = row.engine
    engine_name = (engine.name or engine.provider) if engine is not None else ""
    return f"{model_name} ({engine_name})" if engine_name else model_name


def _embedding_dim(row: ModelRegistry) -> int | None:
    extra_config = row.extra_config if isinstance(row.extra_config, dict) else {}
    defaults = extra_config.get("defaults") if isinstance(extra_config.get("defaults"), dict) else {}
    runtime = defaults.get("runtime") if isinstance(defaults.get("runtime"), dict) else {}
    try:
        dim = int(runtime.get("dim") or 0)
    except (TypeError, ValueError):
        return None
    return dim if dim > 0 else None


def _serialize_config(row: KnowledgeRuntimeConfig | None) -> dict[str, Any]:
    if row is None:
        return {
            "id": CONFIG_ROW_ID,
            "enabled": False,
            "embedding_model_registry_id": None,
            "rerank_model_registry_id": None,
            "classification_model_registry_id": None,
            "triple_extractor_model_registry_id": None,
        }
    return {
        "id": row.id,
        "enabled": row.enabled,
        "embedding_model_registry_id": row.embedding_model_registry_id,
        "rerank_model_registry_id": row.rerank_model_registry_id,
        "classification_model_registry_id": row.classification_model_registry_id,
        "triple_extractor_model_registry_id": row.triple_extractor_model_registry_id,
    }


def _normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "enabled": normalize_bool(payload.get("enabled"), default=False),
        "embedding_model_registry_id": to_optional_int(
            payload.get("embedding_model_registry_id")
        ),
        "rerank_model_registry_id": to_optional_int(
            payload.get("rerank_model_registry_id")
        ),
        "classification_model_registry_id": to_optional_int(
            payload.get("classification_model_registry_id")
        ),
        "triple_extractor_model_registry_id": to_optional_int(
            payload.get("triple_extractor_model_registry_id")
        ),
    }


def _require_model(
    session,
    *,
    model_id: int | None,
    capability: str,
    field_name: str,
    required: bool = False,
) -> None:
    if model_id is None:
        if required:
            raise ValueError(f"{field_name}_required")
        return
    row = session.query(ModelRegistry).filter(ModelRegistry.id == model_id).first()
    if row is None:
        raise ValueError(f"{field_name}_not_found")
    if row.status != "active":
        raise ValueError(f"{field_name}_not_active")
    capabilities = set(normalize_capabilities(row.capabilities))
    if capability not in capabilities:
        raise ValueError(f"{field_name}_capability_invalid")
    if capability == AICapability.EMBEDDING and _embedding_dim(row) is None:
        raise ValueError(f"{field_name}_dim_required")


def get_knowledge_runtime_config() -> dict[str, Any]:
    with SessionLocal() as session:
        row = session.get(KnowledgeRuntimeConfig, CONFIG_ROW_ID)
        return _serialize_config(row)


def list_model_options_for_capability(capability: str) -> list[dict[str, Any]]:
    options: list[dict[str, Any]] = [{"label": "Disabled", "value": ""}]
    with SessionLocal() as session:
        rows = (
            session.query(ModelRegistry)
            .options(
                joinedload(ModelRegistry.engine),
                joinedload(ModelRegistry.available_model),
            )
            .outerjoin(EngineRegistry, ModelRegistry.engine_id == EngineRegistry.id)
            .filter(ModelRegistry.status == "active")
            .order_by(ModelRegistry.name.asc(), EngineRegistry.name.asc())
            .all()
        )
    for row in rows:
        capabilities = set(normalize_capabilities(row.capabilities))
        if capability not in capabilities:
            continue
        options.append({"label": _model_label(row), "value": row.id})
    return options


def knowledge_config_form_model() -> list[dict[str, Any]]:
    config = get_knowledge_runtime_config()
    embedding_model_registry_id = config["embedding_model_registry_id"]
    rerank_model_registry_id = config["rerank_model_registry_id"]
    classification_model_registry_id = config["classification_model_registry_id"]
    triple_extractor_model_registry_id = config["triple_extractor_model_registry_id"]
    return [
        {
            "name": "enabled",
            "label": "Enable knowledge",
            "type": "toggle",
            "value": config["enabled"],
        },
        {
            "name": "embedding_model_registry_id",
            "label": "Embedding model",
            "type": "select",
            "value": (
                embedding_model_registry_id
                if embedding_model_registry_id is not None
                else ""
            ),
            "options": list_model_options_for_capability(AICapability.EMBEDDING),
        },
        {
            "name": "rerank_model_registry_id",
            "label": "Rerank model",
            "type": "select",
            "value": (
                rerank_model_registry_id
                if rerank_model_registry_id is not None
                else ""
            ),
            "options": list_model_options_for_capability(AICapability.RERANKING),
        },
        {
            "name": "classification_model_registry_id",
            "label": "Classification model",
            "type": "select",
            "value": (
                classification_model_registry_id
                if classification_model_registry_id is not None
                else ""
            ),
            "options": list_model_options_for_capability(AICapability.CLASSIFICATION),
        },
        {
            "name": "triple_extractor_model_registry_id",
            "label": "Triple extractor model",
            "type": "select",
            "value": (
                triple_extractor_model_registry_id
                if triple_extractor_model_registry_id is not None
                else ""
            ),
            "options": list_model_options_for_capability(AICapability.TRIPLES_EXTRACTOR),
        },
    ]


def count_existing_embeddings() -> int:
    with SessionLocal() as session:
        return (
            session.query(KnowledgeItemRecord)
            .filter(KnowledgeItemRecord.embedding_vector_json.isnot(None))
            .count()
        )


def update_knowledge_runtime_config(
    payload: dict[str, Any],
    *,
    confirm_embedding_model_change: bool = False,
) -> dict[str, Any]:
    normalized = _normalize_payload(payload)
    with SessionLocal() as session:
        current = session.get(KnowledgeRuntimeConfig, CONFIG_ROW_ID)
        previous_embedding_id = (
            current.embedding_model_registry_id if current is not None else None
        )
        if normalized["enabled"] and normalized["embedding_model_registry_id"] is None:
            raise ValueError("embedding_model_registry_id_required")

        _require_model(
            session,
            model_id=normalized["embedding_model_registry_id"],
            capability=AICapability.EMBEDDING,
            field_name="embedding_model_registry_id",
            required=normalized["enabled"],
        )
        _require_model(
            session,
            model_id=normalized["rerank_model_registry_id"],
            capability=AICapability.RERANKING,
            field_name="rerank_model_registry_id",
        )
        _require_model(
            session,
            model_id=normalized["classification_model_registry_id"],
            capability=AICapability.CLASSIFICATION,
            field_name="classification_model_registry_id",
        )
        _require_model(
            session,
            model_id=normalized["triple_extractor_model_registry_id"],
            capability=AICapability.TRIPLES_EXTRACTOR,
            field_name="triple_extractor_model_registry_id",
        )

        next_embedding_id = normalized["embedding_model_registry_id"]
        if (
            normalized["enabled"]
            and previous_embedding_id is not None
            and next_embedding_id != previous_embedding_id
            and not confirm_embedding_model_change
            and count_existing_embeddings() > 0
        ):
            raise RuntimeError("knowledge_embedding_model_change_requires_rebuild")

        if current is None:
            current = KnowledgeRuntimeConfig(id=CONFIG_ROW_ID)
            session.add(current)

        current.enabled = normalized["enabled"]
        current.embedding_model_registry_id = normalized["embedding_model_registry_id"]
        current.rerank_model_registry_id = normalized["rerank_model_registry_id"]
        current.classification_model_registry_id = normalized[
            "classification_model_registry_id"
        ]
        current.triple_extractor_model_registry_id = normalized[
            "triple_extractor_model_registry_id"
        ]
        session.commit()
        session.refresh(current)
        return _serialize_config(current)
