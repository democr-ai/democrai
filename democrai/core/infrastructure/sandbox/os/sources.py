from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from sqlalchemy.exc import OperationalError

from democrai.core.infrastructure.database import SessionLocal
from democrai.core.infrastructure.database.models import (
    EngineRegistry,
    ExternalAccessApproval,
    ExternalAccessRequest,
    McpServerRegistry,
)
from democrai.core.application.ai.engine.access_constants import (
    DEFAULT_ENGINE_INSTALL_RECEIVE_URLS,
)
from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.runtime.foundation.paths import (
    get_runtime_engine_dirs,
    get_runtime_extractor_dirs,
    get_runtime_module_dirs,
)

from .models import NetworkEndpoint
from .normalize import dedupe_endpoints, endpoint_from_target
from .observed import collect_observed_runtime_endpoints


_REMOTE_DATABASE_TYPES = {"postgres", "postgresql", "supabase"}
_REMOTE_MEDIA_TYPES = {"s3", "minio"}
_REMOTE_KG_TYPES = {"neo4j"}
_REMOTE_VECTOR_TYPES = {
    "milvus",
    "qdrant",
    "weaviate",
    "pinecone",
    "postgres",
    "pgvector",
}
_REMOTE_OBSERVABILITY_TYPES = {"postgres", "postgresql", "clickhouse"}
_REMOTE_SESSION_PROVIDERS = {"redis", "postgres", "postgresql"}
_REMOTE_KNOWLEDGE_PROVIDERS = {"openai", "openai_compatible", "ollama"}


def _load_json_file(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _iter_manifest_payloads(root: Path) -> Iterable[tuple[Path, dict[str, Any]]]:
    if not root.exists() or not root.is_dir():
        return []
    items: list[tuple[Path, dict[str, Any]]] = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        manifest_path = entry / "manifest.json"
        if not manifest_path.exists():
            continue
        manifest = _load_json_file(manifest_path)
        if manifest is None:
            continue
        items.append((entry, manifest))
    return items


def _config_get(config: Any, key: str, default: Any = None) -> Any:
    getter = getattr(config, "get", None)
    if callable(getter):
        return getter(key, default)
    return default


def _targets_from_iterable(
    values: Iterable[Any],
    *,
    source: str,
    purpose: str,
) -> list[NetworkEndpoint]:
    endpoints: list[NetworkEndpoint] = []
    for value in values:
        endpoint = endpoint_from_target(
            str(value or "").strip(),
            source=source,
            purpose=purpose,
        )
        if endpoint is not None:
            endpoints.append(endpoint)
    return dedupe_endpoints(endpoints)


def _host_port_endpoint(
    host: Any,
    port: Any,
    *,
    source: str,
    purpose: str,
) -> NetworkEndpoint | None:
    resolved_host = str(host or "").strip()
    if not resolved_host:
        return None
    return endpoint_from_target(
        f"{resolved_host}:{port}",
        source=source,
        purpose=purpose,
    )


def _config_url_endpoint(
    config: Any,
    *,
    key: str,
    source: str,
    purpose: str,
) -> NetworkEndpoint | None:
    value = _config_get(config, key)
    if value is None:
        return None
    return endpoint_from_target(
        str(value).strip(),
        source=source,
        purpose=purpose,
    )


def _allowed_config_url_keys(section: Any) -> list[str]:
    if not isinstance(section, dict):
        return []
    raw = section.get("allowed_config_urls")
    if isinstance(raw, str):
        key = raw.strip()
        return [key] if key else []
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    return []


def _config_urls_by_keys(config: Any, keys: list[str]) -> list[str]:
    if not isinstance(config, dict):
        return []
    values: list[str] = []
    for key in keys:
        current = config.get(key)
        if isinstance(current, str):
            candidate = current.strip()
            if candidate:
                values.append(candidate)
            continue
        if isinstance(current, list):
            for item in current:
                candidate = str(item or "").strip()
                if candidate:
                    values.append(candidate)
    return values


def _config_url_target(config: Any, key: str) -> str:
    value = _config_get(config, key)
    if value is None:
        return ""
    return str(value).strip()


def collect_config_access_targets(config: Any) -> list[str]:
    if config is None:
        return []
    targets: list[str] = []

    database_type = str(_config_get(config, "database.type", "") or "").strip().lower()
    if database_type in _REMOTE_DATABASE_TYPES:
        target = _config_url_target(config, "database.url")
        if target:
            targets.append(target)

    data_type = str(_config_get(config, "database.data_type", "") or "").strip().lower()
    if data_type in _REMOTE_DATABASE_TYPES:
        target = _config_url_target(config, "database.data_url")
        if target:
            targets.append(target)

    media_type = (
        str(_config_get(config, "storage.media.type", "") or "").strip().lower()
    )
    if media_type in _REMOTE_MEDIA_TYPES:
        target = _config_url_target(config, "storage.media.endpoint_url")
        if target:
            targets.append(target)

    kg_type = str(_config_get(config, "storage.kg.type", "") or "").strip().lower()
    if kg_type in _REMOTE_KG_TYPES:
        target = _config_url_target(config, "storage.kg.uri")
        if target:
            targets.append(target)

    vector_type = (
        str(_config_get(config, "storage.vector.type", "") or "").strip().lower()
    )
    if vector_type in _REMOTE_VECTOR_TYPES:
        target = _config_url_target(config, "storage.vector.url")
        if target:
            targets.append(target)
        else:
            host = str(_config_get(config, "storage.vector.host") or "").strip()
            port = str(_config_get(config, "storage.vector.port") or "").strip()
            if host and port:
                targets.append(f"{host}:{port}")

    observability_type = (
        str(_config_get(config, "storage.observability.type", "") or "").strip().lower()
    )
    if observability_type in _REMOTE_OBSERVABILITY_TYPES:
        target = _config_url_target(config, "storage.observability.url")
        if target:
            targets.append(target)

    if bool(_config_get(config, "storage.observability.exporters.otlp.enabled", False)):
        target = _config_url_target(
            config,
            "storage.observability.exporters.otlp.endpoint",
        )
        if target:
            targets.append(target)

    logging_provider = (
        str(_config_get(config, "logging.provider", "") or "").strip().lower()
    )
    if logging_provider == "http":
        target = _config_url_target(config, "logging.url")
        if target:
            targets.append(target)

    if bool(_config_get(config, "network.redis.enabled", False)):
        target = _config_url_target(config, "network.redis.url")
        if target:
            targets.append(target)

    target = _config_url_target(config, "session.redis.url")
    if target:
        targets.append(target)

    ui_state_provider = (
        str(_config_get(config, "session.ui_state.provider", "") or "").strip().lower()
    )
    if ui_state_provider in _REMOTE_SESSION_PROVIDERS:
        target = _config_url_target(config, "session.ui_state.url")
        if target:
            targets.append(target)

    cache_provider = (
        str(_config_get(config, "session.cache.provider", "") or "").strip().lower()
    )
    if cache_provider == "redis":
        target = _config_url_target(config, "session.redis.url")
        if target:
            targets.append(target)

    deduped: list[str] = []
    seen: set[str] = set()
    for target in targets:
        if target in seen:
            continue
        seen.add(target)
        deduped.append(target)
    return deduped


def collect_config_endpoints(config: Any) -> list[NetworkEndpoint]:
    if config is None:
        return []
    endpoints: list[NetworkEndpoint] = []

    database_type = str(_config_get(config, "database.type", "") or "").strip().lower()
    if database_type in _REMOTE_DATABASE_TYPES:
        endpoint = _config_url_endpoint(
            config,
            key="database.url",
            source="config.database",
            purpose="database",
        )
        if endpoint is not None:
            endpoints.append(endpoint)

    data_type = str(_config_get(config, "database.data_type", "") or "").strip().lower()
    if data_type in _REMOTE_DATABASE_TYPES:
        endpoint = _config_url_endpoint(
            config,
            key="database.data_url",
            source="config.database_data",
            purpose="database",
        )
        if endpoint is not None:
            endpoints.append(endpoint)

    media_type = (
        str(_config_get(config, "storage.media.type", "") or "").strip().lower()
    )
    if media_type in _REMOTE_MEDIA_TYPES:
        endpoint = _config_url_endpoint(
            config,
            key="storage.media.endpoint_url",
            source="config.storage_media",
            purpose="storage",
        )
        if endpoint is not None:
            endpoints.append(endpoint)

    kg_type = str(_config_get(config, "storage.kg.type", "") or "").strip().lower()
    if kg_type in _REMOTE_KG_TYPES:
        endpoint = _config_url_endpoint(
            config,
            key="storage.kg.uri",
            source="config.storage_kg",
            purpose="kg",
        )
        if endpoint is not None:
            endpoints.append(endpoint)

    vector_type = (
        str(_config_get(config, "storage.vector.type", "") or "").strip().lower()
    )
    if vector_type in _REMOTE_VECTOR_TYPES:
        endpoint = _host_port_endpoint(
            _config_get(config, "storage.vector.host"),
            _config_get(config, "storage.vector.port"),
            source="config.storage_vector",
            purpose="vector",
        )
        if endpoint is not None:
            endpoints.append(endpoint)
        endpoint = _config_url_endpoint(
            config,
            key="storage.vector.url",
            source="config.storage_vector",
            purpose="vector",
        )
        if endpoint is not None:
            endpoints.append(endpoint)

    observability_type = (
        str(_config_get(config, "storage.observability.type", "") or "").strip().lower()
    )
    if observability_type in _REMOTE_OBSERVABILITY_TYPES:
        endpoint = _config_url_endpoint(
            config,
            key="storage.observability.url",
            source="config.storage_observability",
            purpose="observability",
        )
        if endpoint is not None:
            endpoints.append(endpoint)

    if bool(_config_get(config, "storage.observability.exporters.otlp.enabled", False)):
        endpoint = _config_url_endpoint(
            config,
            key="storage.observability.exporters.otlp.endpoint",
            source="config.storage_observability_otlp",
            purpose="observability",
        )
        if endpoint is not None:
            endpoints.append(endpoint)

    logging_provider = (
        str(_config_get(config, "logging.provider", "") or "").strip().lower()
    )
    if logging_provider == "http":
        endpoint = _config_url_endpoint(
            config,
            key="logging.url",
            source="config.logging",
            purpose="logging",
        )
        if endpoint is not None:
            endpoints.append(endpoint)

    if bool(_config_get(config, "network.redis.enabled", False)):
        endpoint = _config_url_endpoint(
            config,
            key="network.redis.url",
            source="config.network_redis",
            purpose="redis",
        )
        if endpoint is not None:
            endpoints.append(endpoint)

    endpoint = _config_url_endpoint(
        config,
        key="session.redis.url",
        source="config.session_redis",
        purpose="redis",
    )
    if endpoint is not None:
        endpoints.append(endpoint)

    ui_state_provider = (
        str(_config_get(config, "session.ui_state.provider", "") or "").strip().lower()
    )
    if ui_state_provider in _REMOTE_SESSION_PROVIDERS:
        endpoint = _config_url_endpoint(
            config,
            key="session.ui_state.url",
            source="config.session_ui_state",
            purpose="session",
        )
        if endpoint is not None:
            endpoints.append(endpoint)

    cache_provider = (
        str(_config_get(config, "session.cache.provider", "") or "").strip().lower()
    )
    if cache_provider == "redis":
        endpoint = _config_url_endpoint(
            config,
            key="session.redis.url",
            source="config.session_cache",
            purpose="session",
        )
        if endpoint is not None:
            endpoints.append(endpoint)

    return dedupe_endpoints(endpoints)


def collect_module_endpoints(modules: Any = None) -> list[NetworkEndpoint]:
    endpoints: list[NetworkEndpoint] = []
    roots = [Path(path) for path in get_runtime_module_dirs()]
    seen_modules: set[str] = set()
    for root in roots:
        for _module_dir, manifest in _iter_manifest_payloads(root):
            module_name = str(manifest.get("name") or "").strip().lower()
            if not module_name or module_name in seen_modules:
                continue
            seen_modules.add(module_name)
            network_targets = [
                item["target"]
                for item in manifest.get("access", [])
                if item["resource_type"] == "network"
            ]
            if not network_targets:
                continue
            endpoints.extend(
                _targets_from_iterable(
                    network_targets,
                    source=f"module:{module_name}",
                    purpose="module_manifest",
                )
            )
    return dedupe_endpoints(endpoints)


def collect_engine_endpoints(engines: Iterable[Any] | None) -> list[NetworkEndpoint]:
    endpoints: list[NetworkEndpoint] = []
    engine_roots = [Path(path) for path in get_runtime_engine_dirs()]
    manifests_by_engine_id: dict[str, dict[str, Any]] = {}
    for engine_root in engine_roots:
        for _engine_dir, manifest in _iter_manifest_payloads(engine_root):
            engine_id = str(manifest.get("id") or "").strip().lower()
            if not engine_id or engine_id in manifests_by_engine_id:
                continue
            manifests_by_engine_id[engine_id] = manifest
            install_section = (
                manifest.get("install") if isinstance(manifest, dict) else {}
            )
            runtime_section = (
                manifest.get("runtime") if isinstance(manifest, dict) else {}
            )
            endpoints.extend(
                _targets_from_iterable(
                    [
                        item["target"]
                        for item in (install_section or {}).get("access", [])
                        if item["resource_type"] == "network"
                    ],
                    source=f"engine:{engine_id}",
                    purpose="engine_install_manifest",
                )
            )
            endpoints.extend(
                _targets_from_iterable(
                    DEFAULT_ENGINE_INSTALL_RECEIVE_URLS,
                    source=f"engine:{engine_id}",
                    purpose="engine_install_default",
                )
            )
            endpoints.extend(
                _targets_from_iterable(
                    [
                        item["target"]
                        for item in (runtime_section or {}).get("access", [])
                        if item["resource_type"] == "network"
                    ],
                    source=f"engine:{engine_id}",
                    purpose="engine_runtime_manifest",
                )
            )

    engine_rows: list[Any] = []
    if engines is not None:
        engine_rows = list(engines or [])
    elif getattr(app_ctx(), "db", None) is not None:
        try:
            with SessionLocal() as session:
                engine_rows = list(session.query(EngineRegistry).all())
        except OperationalError:
            engine_rows = []

    for row in engine_rows:
        if isinstance(row, dict):
            provider = str(row.get("provider") or "").strip().lower()
            config = row.get("config")
        else:
            provider = str(getattr(row, "provider", "") or "").strip().lower()
            config = getattr(row, "config", None)
        if not provider or not isinstance(config, dict):
            continue
        manifest = manifests_by_engine_id.get(provider) or {}
        install_section = manifest.get("install") if isinstance(manifest, dict) else {}
        runtime_section = manifest.get("runtime") if isinstance(manifest, dict) else {}
        endpoints.extend(
            _targets_from_iterable(
                _config_urls_by_keys(config, _allowed_config_url_keys(install_section)),
                source=f"engine:{provider}",
                purpose="engine_install_config",
            )
        )
        endpoints.extend(
            _targets_from_iterable(
                _config_urls_by_keys(config, _allowed_config_url_keys(runtime_section)),
                source=f"engine:{provider}",
                purpose="engine_runtime_config",
            )
        )
    return dedupe_endpoints(endpoints)


def collect_extractor_endpoints(
    extractors: Iterable[Any] | None,
) -> list[NetworkEndpoint]:
    endpoints: list[NetworkEndpoint] = []
    extractor_roots = [Path(path) for path in get_runtime_extractor_dirs()]
    seen_extractors: set[str] = set()
    for extractor_root in extractor_roots:
        for _extractor_dir, manifest in _iter_manifest_payloads(extractor_root):
            extractor_id = str(manifest.get("id") or "").strip().lower()
            if not extractor_id or extractor_id in seen_extractors:
                continue
            seen_extractors.add(extractor_id)
            install_section = (
                manifest.get("install") if isinstance(manifest, dict) else {}
            )
            runtime_section = (
                manifest.get("runtime") if isinstance(manifest, dict) else {}
            )
            endpoints.extend(
                _targets_from_iterable(
                    [
                        item["target"]
                        for item in (install_section or {}).get("access", [])
                        if item["resource_type"] == "network"
                    ],
                    source=f"extractor:{extractor_id}",
                    purpose="extractor_install_manifest",
                )
            )
            endpoints.extend(
                _targets_from_iterable(
                    [
                        item["target"]
                        for item in (runtime_section or {}).get("access", [])
                        if item["resource_type"] == "network"
                    ],
                    source=f"extractor:{extractor_id}",
                    purpose="extractor_runtime_manifest",
                )
            )
    return dedupe_endpoints(endpoints)


def collect_mcp_server_endpoints(
    mcp_servers: Iterable[Any] | None,
) -> list[NetworkEndpoint]:
    records: list[Any] = []
    if mcp_servers is not None:
        records = list(mcp_servers or [])
    elif getattr(app_ctx(), "db", None) is not None:
        try:
            with SessionLocal() as session:
                records = (
                    session.query(McpServerRegistry)
                    .filter(McpServerRegistry.enabled.is_(True))
                    .all()
                )
        except OperationalError:
            records = []

    endpoints: list[NetworkEndpoint] = []
    for row in records:
        if isinstance(row, dict):
            enabled = bool(row.get("enabled"))
            endpoint_url = str(row.get("endpoint_url") or "").strip()
            name = str(row.get("name") or "").strip().lower()
        else:
            enabled = bool(getattr(row, "enabled", False))
            endpoint_url = str(getattr(row, "endpoint_url", "") or "").strip()
            name = str(getattr(row, "name", "") or "").strip().lower()
        if not enabled or not endpoint_url:
            continue
        endpoint = endpoint_from_target(
            endpoint_url,
            source=f"mcp:{name or 'server'}",
            purpose="mcp_runtime",
        )
        if endpoint is not None:
            endpoints.append(endpoint)
    return dedupe_endpoints(endpoints)


def collect_access_policy_approval_endpoints(
    approvals: Iterable[Any] | None,
) -> list[NetworkEndpoint]:
    if approvals is None:
        if getattr(app_ctx(), "db", None) is None:
            return []
        try:
            with SessionLocal() as session:
                approvals = list(session.query(ExternalAccessApproval).all())
        except OperationalError:
            approvals = []
    endpoints: list[NetworkEndpoint] = []
    for approval in list(approvals or []):
        resource_type = (
            str(getattr(approval, "resource_type", "") or "").strip().lower()
        )
        if resource_type != "network":
            continue
        subject_type = str(getattr(approval, "subject_type", "") or "").strip().lower()
        subject_name = str(getattr(approval, "subject_name", "") or "").strip().lower()
        endpoint = endpoint_from_target(
            str(getattr(approval, "target", "") or "").strip(),
            source=f"{subject_type}:{subject_name}" if subject_type and subject_name else "access_policy_approvals",
            purpose="db_approval",
        )
        if endpoint is not None:
            endpoints.append(endpoint)
    return dedupe_endpoints(endpoints)


def collect_access_policy_session_approval_endpoints(
    approvals: Iterable[Any] | None,
) -> list[NetworkEndpoint]:
    if approvals is None:
        if getattr(app_ctx(), "db", None) is None:
            return []
        try:
            with SessionLocal() as session:
                approvals = (
                    session.query(ExternalAccessRequest)
                    .filter(ExternalAccessRequest.status == "session")
                    .all()
                )
        except OperationalError:
            approvals = []
    endpoints: list[NetworkEndpoint] = []
    for approval in list(approvals or []):
        resource_type = (
            str(getattr(approval, "resource_type", "") or "").strip().lower()
        )
        if resource_type != "network":
            continue
        subject_type = str(getattr(approval, "subject_type", "") or "").strip().lower()
        subject_name = str(getattr(approval, "subject_name", "") or "").strip().lower()
        endpoint = endpoint_from_target(
            str(getattr(approval, "target", "") or "").strip(),
            source=f"{subject_type}:{subject_name}" if subject_type and subject_name else "access_policy_session_approvals",
            purpose="db_session_approval",
        )
        if endpoint is not None:
            endpoints.append(endpoint)
    return dedupe_endpoints(endpoints)


def collect_observed_endpoints(config: Any = None) -> list[NetworkEndpoint]:
    return dedupe_endpoints(collect_observed_runtime_endpoints(config))
