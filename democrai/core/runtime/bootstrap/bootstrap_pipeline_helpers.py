from __future__ import annotations

from democrai.core.application.knowledge.classification import (
    ModelRegistryClassificationProvider,
)
from democrai.core.application.knowledge.configuration import get_knowledge_runtime_config
from democrai.core.application.knowledge.embedding import ModelRegistryEmbeddingProvider
from democrai.core.application.knowledge.ingestion import KnowledgeIngestionFacade
from democrai.core.application.knowledge.reranking import ModelRegistryRerankProvider
from democrai.core.application.knowledge.repository import KnowledgeRepository
from democrai.core.application.knowledge.runtime import KnowledgeRuntime
from democrai.core.application.knowledge.service import KnowledgeService
from democrai.core.application.knowledge.triples import ModelRegistryTripleExtractor
from democrai.core.infrastructure.database import SessionLocal
from democrai.core.infrastructure.database.models import ModelRegistry
from democrai.core.infrastructure.storage.vector.base import IndexSpec
from democrai.core.infrastructure.storage.vector.base import Metric
from democrai.core.platform.utils.normalize import normalize_bool
from democrai.core.runtime.foundation.paths import (
    get_runtime_module_dirs,
)


def init_knowledge(ctx) -> None:
    """Initialize knowledge services from database-backed runtime config."""
    ctx.knowledge_service = None
    ctx.knowledge_ingestion = None
    ctx.knowledge_runtime = None
    config = get_knowledge_runtime_config()
    if not bool(config.get("enabled")):
        return

    embedding_model_id = config.get("embedding_model_registry_id")
    if embedding_model_id is None:
        raise RuntimeError("knowledge_embedding_model_registry_id_required")
    embedding_model = _knowledge_model_row(embedding_model_id)
    embedding_dim = _knowledge_embedding_dim(embedding_model)
    if embedding_dim is None:
        raise RuntimeError("knowledge_embedding_model_dim_required")

    embedding_provider = ModelRegistryEmbeddingProvider(
        model_registry_id=embedding_model.id,
        dim=int(embedding_dim),
        model_id=str(embedding_model.id),
        model_version=_model_version(embedding_model),
    )
    rerank_provider = None
    rerank_model_id = config.get("rerank_model_registry_id")
    if rerank_model_id is not None:
        rerank_model = _knowledge_model_row(rerank_model_id)
        rerank_provider = ModelRegistryRerankProvider(
            model_registry_id=rerank_model.id,
            model_id=str(rerank_model.id),
            model_version=_model_version(rerank_model),
            runtime_options=_knowledge_runtime_options(
                rerank_model,
                ("top_k", "max_tokens_per_doc"),
            ),
        )
    classification_provider = None
    classification_model_id = config.get("classification_model_registry_id")
    if classification_model_id is not None:
        classification_model = _knowledge_model_row(classification_model_id)
        classification_provider = ModelRegistryClassificationProvider(
            model_registry_id=classification_model.id,
            model_id=str(classification_model.id),
            model_version=_model_version(classification_model),
            runtime_options=_knowledge_runtime_options(
                classification_model,
                ("top_k", "function_to_apply"),
            ),
        )
    triple_extractor = None
    triple_model_id = config.get("triple_extractor_model_registry_id")
    if triple_model_id is not None:
        triple_model = _knowledge_model_row(triple_model_id)
        triple_extractor = ModelRegistryTripleExtractor(
            model_registry_id=triple_model.id,
            model_id=str(triple_model.id),
            model_version=_model_version(triple_model),
            **_knowledge_triple_extractor_config(triple_model),
        )

    vector_cfg = _knowledge_vector_config(ctx)
    vector_spec = IndexSpec(
        tenant_id=str(vector_cfg["tenant_id"]),
        app_id=str(vector_cfg["app_id"]),
        name=str(vector_cfg["name"]),
        dim=int(embedding_dim),
        metric=Metric(str(vector_cfg["metric"])),
        embedding_model_id=str(embedding_model.id),
        embedding_model_version=_model_version(embedding_model),
    )
    repository = KnowledgeRepository(SessionLocal)
    ctx.knowledge_service = KnowledgeService(
        repository=repository,
        vector_store=ctx.vector_store,
        kg_store=ctx.kg_store,
        vector_spec=vector_spec,
        embedding_provider=embedding_provider,
        rerank_provider=rerank_provider,
        classification_provider=classification_provider,
        triple_extractor=triple_extractor,
        graph_traversal_depth=int(
            ctx.config.get("knowledge.retrieval.graph_traversal_depth_default", 2)
        ),
        graph_expansion_limit=int(
            ctx.config.get("knowledge.retrieval.graph_expansion_limit", 8)
        ),
        graph_score_weight=float(
            ctx.config.get("knowledge.retrieval.graph_score_weight", 0.2)
        ),
    )
    ctx.knowledge_ingestion = KnowledgeIngestionFacade(service=ctx.knowledge_service)
    ctx.knowledge_runtime = KnowledgeRuntime(
        ctx.knowledge_service,
        poll_interval_seconds=float(
            ctx.config.get("knowledge.runtime.poll_interval_seconds", 1.0)
        ),
        batch_size=int(ctx.config.get("knowledge.runtime.batch_size", 16)),
        lease_seconds=int(ctx.config.get("knowledge.runtime.lease_seconds", 30)),
        max_attempts=int(ctx.config.get("knowledge.runtime.max_attempts", 8)),
    )


def _knowledge_model_row(model_registry_id: int):
    with SessionLocal() as session:
        row = session.get(ModelRegistry, model_registry_id)
        if row is None:
            raise RuntimeError(
                f"knowledge_model_registry_row_not_found:{model_registry_id}"
            )
        session.expunge(row)
        return row


def _model_version(row: ModelRegistry) -> str:
    version = row.version
    return version if isinstance(version, str) and version else "1"


def _knowledge_embedding_dim(row: ModelRegistry) -> int | None:
    extra_config = row.extra_config if isinstance(row.extra_config, dict) else {}
    defaults = extra_config.get("defaults") if isinstance(extra_config.get("defaults"), dict) else {}
    runtime = defaults.get("runtime") if isinstance(defaults.get("runtime"), dict) else {}
    try:
        raw_dim = runtime.get("dim")
        dim = 0 if raw_dim is None else int(raw_dim)
    except (TypeError, ValueError):
        return None
    return dim if dim > 0 else None


def _knowledge_vector_config(ctx) -> dict[str, object]:
    return {
        "tenant_id": ctx.config.get("knowledge.vector_index.tenant_id", "democrai"),
        "app_id": ctx.config.get("knowledge.vector_index.app_id", "knowledge"),
        "name": ctx.config.get("knowledge.vector_index.name", "items"),
        "metric": ctx.config.get("knowledge.vector_index.metric", "cosine"),
    }


def _knowledge_triple_extractor_config(row: ModelRegistry) -> dict[str, object]:
    runtime = _knowledge_runtime_options(
        row,
        ("max_entities", "max_relations", "temperature", "max_tokens"),
    )
    return {key: value for key, value in runtime.items() if value not in (None, "")}


def _knowledge_runtime_options(
    row: ModelRegistry,
    keys: tuple[str, ...],
) -> dict[str, object]:
    extra_config = row.extra_config if isinstance(row.extra_config, dict) else {}
    defaults = extra_config.get("defaults") if isinstance(extra_config.get("defaults"), dict) else {}
    runtime = defaults.get("runtime") if isinstance(defaults.get("runtime"), dict) else {}
    return {key: runtime[key] for key in keys if key in runtime}


def init_modules(ctx, args, *, load_ui: bool = True) -> None:
    configured_module_paths = getattr(args, "module_paths", None)
    raw_module_paths = (
        get_runtime_module_dirs()
        if configured_module_paths is None
        else configured_module_paths
    )
    runtime_module_paths = tuple(
        path.strip()
        for path in raw_module_paths
        if isinstance(path, str) and path.strip()
    )
    raw_trust_mode = ctx.config.get("modules.trust_mode", "all")
    trust_mode = (
        raw_trust_mode.strip().lower()
        if isinstance(raw_trust_mode, str) and raw_trust_mode.strip()
        else "all"
    )
    allow_user_modules_value = ctx.config.get("modules.allow_user_modules")
    if allow_user_modules_value is None:
        allow_user_modules = trust_mode != "trusted_only"
    else:
        allow_user_modules = normalize_bool(
            allow_user_modules_value, default=(trust_mode != "trusted_only")
        )

    trusted_modules_raw = ctx.config.get("modules.trusted_modules", [])
    if isinstance(trusted_modules_raw, (list, tuple, set)):
        trusted_modules = [
            item.strip()
            for item in trusted_modules_raw
            if isinstance(item, str) and item.strip()
        ]
    elif trusted_modules_raw is None:
        trusted_modules = []
    else:
        trusted_modules = [
            item.strip() for item in str(trusted_modules_raw).split(",") if item.strip()
        ]

    ctx.modules.configure_trust(
        trust_mode=trust_mode,
        allow_user_modules=allow_user_modules,
        trusted_modules=trusted_modules,
    )
    ctx.modules.enable_runtime()
    for modules_dir in runtime_module_paths:
        ctx.modules.discover_modules(
            modules_dir, is_builtin=True, load_ui=load_ui
        )
    if allow_user_modules:
        for modules_dir in runtime_module_paths:
            ctx.modules.discover_modules(
                modules_dir, is_builtin=False, load_ui=load_ui
            )
