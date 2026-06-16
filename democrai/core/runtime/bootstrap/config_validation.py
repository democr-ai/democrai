from __future__ import annotations

import json
import os
from dataclasses import asdict
from dataclasses import dataclass, field

from democrai.core.platform.config.yaml_config import YamlConfigProvider
from democrai.core.platform.utils.normalize import FALSE_STRINGS, TRUE_STRINGS, normalize_key
from democrai.core.platform.utils.timezone import validate_timezone_name
from democrai.core.runtime.foundation.paths import get_data_dir


@dataclass(frozen=True)
class ConfigValidationIssue:
    level: str
    message: str


@dataclass(frozen=True)
class ConfigValidationResult:
    config_path: str
    errors: list[ConfigValidationIssue] = field(default_factory=list)
    warnings: list[ConfigValidationIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict:
        return {
            "config_path": self.config_path,
            "ok": self.ok,
            "warnings": [asdict(item) for item in self.warnings],
            "errors": [asdict(item) for item in self.errors],
        }


def _as_issue(level: str, message: str) -> ConfigValidationIssue:
    return ConfigValidationIssue(level=level, message=message)


def _default_config_path() -> str:
    return os.path.join(get_data_dir(), "config.yaml")


def validate_config_file(config_path: str | None = None) -> ConfigValidationResult:
    path = config_path or _default_config_path()
    provider = YamlConfigProvider(path)
    return validate_config_provider(provider, config_path=path)


def validate_config_provider(provider, *, config_path: str = "<memory>") -> ConfigValidationResult:
    errors: list[ConfigValidationIssue] = []
    warnings: list[ConfigValidationIssue] = []

    def require_one_of(key: str, allowed: set[str]) -> str | None:
        value = provider.get(key)
        if value is None:
            return None
        normalized = str(value).strip().lower()
        if normalized not in allowed:
            errors.append(
                _as_issue(
                    "error",
                    f"{key} must be one of {sorted(allowed)}, got {value!r}",
                )
            )
            return None
        return normalized

    db_type = require_one_of("database.type", {"sqlite", "postgres"})
    data_type = require_one_of("database.data_type", {"sqlite", "postgres", "supabase"})
    media_type = require_one_of("storage.media.type", {"local", "s3"})
    kg_type = require_one_of("storage.kg.type", {"sqlite", "ladybug", "neo4j"})
    vector_type = require_one_of("storage.vector.type", {"sqlite-vec", "milvus", "pinecone"})
    obs_type = require_one_of("storage.observability.type", {"sqlite", "postgres", "clickhouse"})

    identity_provider = require_one_of("session.identity.provider", {"sqlite", "redis"})
    ui_state_provider = require_one_of("session.ui_state.provider", {"sqlite", "postgres", "redis"})
    cache_provider = require_one_of("session.cache.provider", {"memory", "redis"})
    require_one_of("network.ws.codec", {"json", "deflate-json"})
    logging_provider = require_one_of("logging.provider", {"local", "http"})
    require_one_of("logging.method", {"get", "post"})
    require_one_of("modules.trust_mode", {"all", "trusted_only"})

    def require_when(condition: bool, key: str, description: str) -> None:
        if condition and not provider.get(key):
            errors.append(_as_issue("error", f"{key} is required when {description}"))

    require_when(db_type == "postgres", "database.url", "database.type=postgres")
    require_when(
        data_type in {"postgres", "supabase"},
        "database.data_url",
        f"database.data_type={data_type}" if data_type else "database.data_type is remote",
    )
    require_when(obs_type == "postgres", "storage.observability.url", "storage.observability.type=postgres")
    require_when(obs_type == "clickhouse", "storage.observability.url", "storage.observability.type=clickhouse")
    require_when(media_type == "s3", "storage.media.bucket", "storage.media.type=s3")
    require_when(kg_type == "neo4j", "storage.kg.uri", "storage.kg.type=neo4j")
    require_when(kg_type == "neo4j", "storage.kg.user", "storage.kg.type=neo4j")
    require_when(kg_type == "neo4j", "storage.kg.password", "storage.kg.type=neo4j")
    require_when(vector_type == "milvus", "storage.vector.host", "storage.vector.type=milvus")
    require_when(
        vector_type == "pinecone" and not os.getenv("PINECONE_API_KEY"),
        "storage.vector.api_key",
        "storage.vector.type=pinecone",
    )
    require_when(ui_state_provider == "postgres", "session.ui_state.url", "session.ui_state.provider=postgres")
    require_when(logging_provider == "http", "logging.url", "logging.provider=http")

    redis_url = provider.get("session.redis.url") or provider.get("network.redis.url")
    if identity_provider == "redis" or ui_state_provider == "redis" or cache_provider == "redis":
        if not redis_url:
            errors.append(
                _as_issue(
                    "error",
                    "session.redis.url or network.redis.url is required when a session provider uses redis",
                )
            )

    if provider.get("network.redis.enabled") and not provider.get("network.redis.url"):
        errors.append(
            _as_issue(
                "error",
                "network.redis.url is required when network.redis.enabled=true",
            )
        )

    allow_user_modules = provider.get("modules.allow_user_modules")
    if allow_user_modules is not None and not isinstance(allow_user_modules, bool):
        normalized = str(allow_user_modules).strip().lower()
        if normalized not in {"1", "0", "true", "false", "yes", "no", "on", "off"}:
            errors.append(_as_issue("error", "modules.allow_user_modules must be a boolean"))

    trusted_modules = provider.get("modules.trusted_modules")
    if trusted_modules is not None and not isinstance(
        trusted_modules, (list, tuple, set, str)
    ):
        errors.append(
            _as_issue(
                "error",
                "modules.trusted_modules must be a list (or comma-separated string)",
            )
        )

    extra_module_paths = provider.get("modules.extra_paths")
    if extra_module_paths is not None and not isinstance(
        extra_module_paths, (list, tuple, set, str)
    ):
        errors.append(
            _as_issue(
                "error",
                "modules.extra_paths must be a list (or comma-separated string)",
            )
        )

    extra_engine_paths = provider.get("engines.extra_paths")
    if extra_engine_paths is not None and not isinstance(
        extra_engine_paths, (list, tuple, set, str)
    ):
        errors.append(
            _as_issue(
                "error",
                "engines.extra_paths must be a list (or comma-separated string)",
            )
        )

    extra_extractor_paths = provider.get("extractors.extra_paths")
    if extra_extractor_paths is not None and not isinstance(
        extra_extractor_paths, (list, tuple, set, str)
    ):
        errors.append(
            _as_issue(
                "error",
                "extractors.extra_paths must be a list (or comma-separated string)",
            )
        )

    ttl_value = provider.get("session.cache.ttl_seconds")
    if ttl_value is not None:
        try:
            ttl = int(ttl_value)
            if ttl <= 0:
                errors.append(_as_issue("error", "session.cache.ttl_seconds must be > 0"))
        except Exception:
            errors.append(_as_issue("error", "session.cache.ttl_seconds must be an integer"))

    media_remote_cache_ttl = provider.get("storage.media.remote_cache.ttl_seconds")
    if media_remote_cache_ttl is not None:
        try:
            ttl = int(media_remote_cache_ttl)
            if ttl <= 0:
                errors.append(
                    _as_issue("error", "storage.media.remote_cache.ttl_seconds must be > 0")
                )
        except Exception:
            errors.append(
                _as_issue(
                    "error",
                    "storage.media.remote_cache.ttl_seconds must be an integer",
                )
            )

    for key in (
        "session.idle_ttl_seconds",
        "session.absolute_ttl_seconds",
        "session.cleanup_interval_seconds",
        "storage.observability.retention.events_days",
        "storage.observability.retention.audit_days",
        "storage.observability.retention.ai_model_usage_days",
        "storage.observability.retention.export_outbox_days",
        "storage.observability.retention.cleanup_interval_seconds",
        "storage.observability.exporters.outbox.flush_interval_seconds",
    ):
        value = provider.get(key)
        if value is None:
            continue
        try:
            parsed = int(value)
            if parsed <= 0:
                errors.append(_as_issue("error", f"{key} must be > 0"))
        except Exception:
            errors.append(_as_issue("error", f"{key} must be an integer"))

    for key in ("auth.cookie_secure", "auth.cookie_http_only"):
        value = provider.get(key)
        if value is None:
            continue
        if isinstance(value, bool):
            continue
        normalized = str(value).strip().lower()
        if normalized not in {"1", "0", "true", "false", "yes", "no", "on", "off"}:
            errors.append(_as_issue("error", f"{key} must be a boolean"))

    samesite_value = provider.get("auth.cookie_samesite")
    if samesite_value is not None:
        normalized = str(samesite_value).strip().lower()
        if normalized not in {"lax", "strict", "none"}:
            errors.append(
                _as_issue(
                    "error",
                    f"auth.cookie_samesite must be one of ['lax', 'none', 'strict'], got {samesite_value!r}",
                )
            )

    for key in ("auth.jwt_issuer", "auth.jwt_audience", "auth.jwt_tid"):
        value = provider.get(key)
        if value is None:
            continue
        if not str(value).strip():
            errors.append(_as_issue("error", f"{key} must be a non-empty string"))

    jwt_ttl = provider.get("auth.jwt_access_ttl_seconds")
    if jwt_ttl is not None:
        try:
            if int(jwt_ttl) <= 0:
                errors.append(
                    _as_issue("error", "auth.jwt_access_ttl_seconds must be > 0")
                )
        except Exception:
            errors.append(
                _as_issue("error", "auth.jwt_access_ttl_seconds must be an integer")
            )

    def _normalize_listish(value) -> list[str]:
        if value is None:
            return []
        if isinstance(value, (list, tuple, set)):
            return [str(item).strip() for item in value if str(item).strip()]
        return [item.strip() for item in str(value).split(",") if item.strip()]

    cors_enabled = provider.get("http.cors.enabled")
    cors_enabled_normalized = False
    if cors_enabled is not None:
        if isinstance(cors_enabled, bool):
            cors_enabled_normalized = cors_enabled
        else:
            normalized = normalize_key(cors_enabled)
            if normalized in TRUE_STRINGS:
                cors_enabled_normalized = True
            elif normalized in FALSE_STRINGS:
                cors_enabled_normalized = False
            else:
                errors.append(_as_issue("error", "http.cors.enabled must be a boolean"))

    cors_allow_credentials = provider.get("http.cors.allow_credentials")
    cors_allow_credentials_normalized = True
    if cors_allow_credentials is not None:
        if isinstance(cors_allow_credentials, bool):
            cors_allow_credentials_normalized = cors_allow_credentials
        else:
            normalized = normalize_key(cors_allow_credentials)
            if normalized in TRUE_STRINGS:
                cors_allow_credentials_normalized = True
            elif normalized in FALSE_STRINGS:
                cors_allow_credentials_normalized = False
            else:
                errors.append(
                    _as_issue("error", "http.cors.allow_credentials must be a boolean")
                )

    cors_allow_origins = _normalize_listish(provider.get("http.cors.allow_origins"))
    if cors_enabled_normalized and not cors_allow_origins:
        errors.append(
            _as_issue("error", "http.cors.allow_origins is required when http.cors.enabled=true")
        )
    if cors_allow_credentials_normalized and "*" in cors_allow_origins:
        errors.append(
            _as_issue(
                "error",
                "http.cors.allow_origins cannot contain '*' when http.cors.allow_credentials=true",
            )
        )

    timezone_value = provider.get("app.timezone")
    if timezone_value is not None and not validate_timezone_name(str(timezone_value)):
        errors.append(
            _as_issue(
                "error",
                f"app.timezone must be a valid IANA timezone or 'system', got {timezone_value!r}",
            )
        )

    if media_type == "s3":
        media_access_key = provider.get("storage.media.access_key")
        media_secret_key = provider.get("storage.media.secret_key")
        if bool(media_access_key) != bool(media_secret_key):
            errors.append(
                _as_issue(
                    "error",
                    "storage.media.access_key and storage.media.secret_key must be provided together",
                )
            )
        warnings.append(
            _as_issue(
                "warning",
                "storage.media.type=s3 is selected; verify bucket credentials are configured in the active environment",
            )
        )

    if provider.get("storage.observability.exporters.otlp.enabled"):
        require_when(
            True,
            "storage.observability.exporters.otlp.endpoint",
            "storage.observability.exporters.otlp.enabled=true",
        )

    if provider.get("auth.jwt_secret") in (None, "", "change-me-with-a-long-random-secret"):
        errors.append(
            _as_issue(
                "error",
                "auth.jwt_secret is required and cannot use the example placeholder",
            )
        )

    from democrai.core.infrastructure.ai.engine.invocation.config import (
        EngineInvocationRuntimeConfig,
    )

    engine_invocation_config = None
    try:
        engine_invocation_config = EngineInvocationRuntimeConfig.load(provider)
        engine_invocation_config.validate_node_coordination(provider)
    except RuntimeError as exc:
        errors.append(_as_issue("error", str(exc)))

    if (
        engine_invocation_config is not None
        and engine_invocation_config.node_coordination_enabled
    ):
        if media_type == "local":
            warnings.append(
                _as_issue(
                    "warning",
                    "ai.engine_orchestrator.node_coordination.enabled=true with "
                    "storage.media.type=local: the media directory must be a "
                    "shared mount reachable by every node (binary payloads are "
                    "passed as storage paths)",
                )
            )
    try:
        from democrai.core.infrastructure.ai.engine.invocation.orchestrator import (
            EngineOrchestratorProviderResolver,
        )
        from democrai.core.infrastructure.ai.engine.response.config import (
            EngineResponseStreamConfig,
        )
        from democrai.core.infrastructure.ai.engine.response.factory import (
            EngineResponseStreamFactory,
        )

        EngineOrchestratorProviderResolver.provider_name_from_config(provider)
        if EngineOrchestratorProviderResolver.requires_shared_response_stream_from_config(
            provider
        ):
            response_stream_config = EngineResponseStreamConfig.load(provider)
            if not EngineResponseStreamFactory.has_provider(
                response_stream_config.provider_type
            ):
                errors.append(
                    _as_issue(
                        "error",
                        "ai.engine_orchestrator.response_stream.type is not a "
                        "registered engine response stream provider",
                    )
                )
            elif not EngineResponseStreamFactory.is_cross_process_provider(
                response_stream_config.provider_type
            ):
                errors.append(
                    _as_issue(
                        "error",
                        "ai.engine_orchestrator.response_stream.type must be a "
                        "cross-process provider when the engine orchestrator "
                        "provider requires queue responses",
                    )
                )
    except RuntimeError as exc:
        errors.append(_as_issue("error", str(exc)))

    return ConfigValidationResult(config_path=config_path, errors=errors, warnings=warnings)


def print_validation_result(result: ConfigValidationResult) -> int:
    print(f"[CONFIG] path={result.config_path}")
    for warning in result.warnings:
        print(f"[WARN] {warning.message}")
    for error in result.errors:
        print(f"[ERROR] {error.message}")
    status = "ok" if result.ok else "invalid"
    print(
        f"[CONFIG] status={status} warnings={len(result.warnings)} errors={len(result.errors)}"
    )
    return 0 if result.ok else 1


def print_validation_result_json(result: ConfigValidationResult) -> int:
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return 0 if result.ok else 1
