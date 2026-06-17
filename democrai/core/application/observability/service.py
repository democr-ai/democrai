from __future__ import annotations

import json
import hashlib
from dataclasses import asdict, is_dataclass
from typing import Any

from sqlalchemy import inspect as sa_inspect

from democrai.core.platform.utils.env import SERVER_NAME
from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.application.observability.trace_archive import (
    archive_queue_payload_hash,
    prepare_pipeline_step_record,
)


_SENSITIVE_KEYS = {
    "password",
    "password_hash",
    "api_key",
    "secret",
    "token",
    "jwt",
    "access_token",
    "refresh_token",
    "embedding_vector_json",
}

_AUDIT_COMPACT_ENTITY_TYPES = {
    "knowledge_items",
    "knowledge_ingestion_requests",
    "session_ui_states",
}

_AUDIT_COMPACT_KEYS = {
    "content",
    "text",
    "markdown",
    "chunks",
    "metadata",
    "context",
    "payload",
    "state",
    "result",
    "input",
    "output",
    "data",
}


def _safe_req_ctx():
    try:
        from democrai.core.runtime.foundation.app import req_ctx

        return req_ctx()
    except Exception:
        return None


def _runtime_node_id() -> str | None:
    ctx = app_ctx()
    configured = str(getattr(ctx, "node_id", "") or "").strip()
    if configured:
        return configured
    cfg = getattr(ctx, "config", None)
    if cfg is not None:
        configured = str(cfg.get("network.node_id", "") or "").strip()
        if configured:
            return configured
    return SERVER_NAME


def _normalize_json(value: Any) -> Any:
    if is_dataclass(value):
        return _normalize_json(asdict(value))
    if isinstance(value, dict):
        normalized = {}
        for key, item in value.items():
            key_text = str(key)
            lowered = key_text.lower()
            if lowered in _SENSITIVE_KEYS or lowered.endswith("_token") or lowered.endswith("_secret"):
                normalized[key_text] = "<redacted>"
                continue
            normalized[key_text] = _normalize_json(item)
        return normalized
    if isinstance(value, (list, tuple, set)):
        return [_normalize_json(item) for item in value]
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _compact_value(value: Any) -> Any:
    normalized = _normalize_json(value)
    text = json.dumps(normalized, ensure_ascii=False, sort_keys=True, default=str)
    return {
        "redacted": "observability_compacted",
        "chars": len(text),
        "bytes": len(text.encode("utf-8")),
        "hash": "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }


def _compact_audit_payload(
    entity_type: str | None,
    payload: dict[str, Any] | None,
    compact_fields: set[str] | None = None,
) -> dict[str, Any]:
    normalized = _normalize_json(payload or {})
    declared_fields = {field.lower() for field in compact_fields or set()}
    compact_entity = entity_type in _AUDIT_COMPACT_ENTITY_TYPES
    if not compact_entity and not declared_fields:
        return normalized
    compacted: dict[str, Any] = {}
    for key, value in normalized.items():
        key_text = str(key)
        lowered = key_text.lower()
        if lowered in declared_fields or (
            compact_entity
            and (
                lowered in _AUDIT_COMPACT_KEYS
                or any(part in lowered for part in _AUDIT_COMPACT_KEYS)
            )
        ):
            compacted[key_text] = _compact_value(value)
        else:
            compacted[key_text] = value
    return compacted


def snapshot_model(obj: Any) -> dict[str, Any]:
    try:
        mapper = sa_inspect(obj).mapper
    except Exception:
        return {}
    payload: dict[str, Any] = {}
    for attr in mapper.column_attrs:
        key = attr.key
        try:
            value = getattr(obj, key)
        except Exception:
            continue
        payload[key] = _normalize_json(value)
    return payload


def snapshot_model_before_update(obj: Any) -> dict[str, Any]:
    current = snapshot_model(obj)
    try:
        state = sa_inspect(obj)
    except Exception:
        return current
    for attr in state.mapper.column_attrs:
        history = state.attrs[attr.key].history
        if history.has_changes() and history.deleted:
            current[attr.key] = _normalize_json(history.deleted[0])
    return current


def resolve_entity_identity(obj: Any) -> tuple[str | None, str | None]:
    try:
        mapper = sa_inspect(obj).mapper
    except Exception:
        return type(obj).__name__, None
    entity_type = getattr(obj, "__tablename__", None) or type(obj).__name__
    pk_values: list[str] = []
    for column in mapper.primary_key:
        key = column.key
        try:
            value = getattr(obj, key)
        except Exception:
            value = None
        if value is not None:
            pk_values.append(str(value))
    return entity_type, ":".join(pk_values) if pk_values else None


def attach_session_audit_actor(
    session: Any,
    *,
    actor_user_id: int | None = None,
    actor_role: str | None = None,
    organization_id: int | None = None,
    session_id: str | None = None,
    request_id: str | None = None,
    correlation_id: str | None = None,
    client_ip: str | None = None,
    channel: str | None = None,
) -> None:
    info = getattr(session, "info", None)
    if info is None:
        try:
            info = {}
            setattr(session, "info", info)
        except Exception:
            return
    info.setdefault("observability_actor", {})
    actor = info["observability_actor"]
    if actor_user_id is not None:
        actor["actor_user_id"] = actor_user_id
    if actor_role is not None:
        actor["actor_role"] = actor_role
    if organization_id is not None:
        actor["organization_id"] = organization_id
    if session_id is not None:
        actor["session_id"] = session_id
    if request_id is not None:
        actor["request_id"] = request_id
    if correlation_id is not None:
        actor["correlation_id"] = correlation_id
    if client_ip is not None:
        actor["client_ip"] = client_ip
    if channel is not None:
        actor["channel"] = channel


class ObservabilityService:
    def _store(self):
        return getattr(app_ctx(), "obs_store", None)

    def _logger(self):
        return getattr(app_ctx(), "logger", None)

    def _request_metadata(self) -> dict[str, Any]:
        ctx = _safe_req_ctx()
        if ctx is None:
            return {}
        return {
            "actor_user_id": ctx.user,
            "actor_role": ctx.role,
            "organization_id": ctx.organization_id,
            "session_id": ctx.session_key,
            "request_id": ctx.request_id,
            "correlation_id": ctx.request_id,
            "client_ip": getattr(ctx, "client_ip", None),
            "channel": ctx.channel,
        }

    def _emit(self, fn_name: str, **kwargs):
        store = self._store()
        if store is None:
            return None
        try:
            return getattr(store, fn_name)(**kwargs)
        except Exception as exc:
            logger = self._logger()
            if logger is not None:
                logger.error(f"[Observability] Failed to persist {fn_name}: {exc}")
            return None

    def record_app_event(self, **kwargs):
        payload = dict(kwargs)
        payload.setdefault("correlation_id", self._request_metadata().get("correlation_id", "system"))
        payload["payload"] = _normalize_json(payload.get("payload"))
        return self._emit("record_event", **payload)

    def record_auth_event(
        self,
        *,
        event_type: str,
        subject_user_id: int | None = None,
        success: bool = True,
        metadata: dict[str, Any] | None = None,
    ):
        request_meta = self._request_metadata()
        merged_metadata = {"subject_user_id": subject_user_id}
        merged_metadata.update(_normalize_json(metadata or {}))
        return self._emit(
            "record_audit_event",
            event_type=event_type,
            actor_user_id=request_meta.get("actor_user_id") or subject_user_id,
            actor_role=request_meta.get("actor_role"),
            organization_id=request_meta.get("organization_id"),
            session_id=request_meta.get("session_id"),
            node_id=_runtime_node_id(),
            request_id=request_meta.get("request_id"),
            correlation_id=request_meta.get("correlation_id"),
            client_ip=request_meta.get("client_ip"),
            channel=request_meta.get("channel"),
            entity_type="auth_session",
            entity_id=str(subject_user_id) if subject_user_id is not None else None,
            operation=event_type,
            status="success" if success else "failure",
            before={},
            after={},
            metadata=merged_metadata,
        )

    def record_db_mutation(
        self,
        *,
        event_type: str = "db_mutation",
        operation: str,
        entity_type: str | None,
        entity_id: str | None,
        before: dict[str, Any] | None,
        after: dict[str, Any] | None,
        metadata: dict[str, Any] | None = None,
        actor: dict[str, Any] | None = None,
        compact_fields: set[str] | None = None,
    ):
        request_meta = self._request_metadata()
        actor_meta = dict(request_meta)
        actor_meta.update({key: value for key, value in (actor or {}).items() if value is not None})
        safe_before = _compact_audit_payload(entity_type, before, compact_fields)
        safe_after = _compact_audit_payload(entity_type, after, compact_fields)
        return self._emit(
            "record_audit_event",
            event_type=event_type,
            actor_user_id=actor_meta.get("actor_user_id"),
            actor_role=actor_meta.get("actor_role"),
            organization_id=actor_meta.get("organization_id"),
            session_id=actor_meta.get("session_id"),
            node_id=actor_meta.get("node_id") or _runtime_node_id(),
            request_id=actor_meta.get("request_id"),
            correlation_id=actor_meta.get("correlation_id"),
            client_ip=actor_meta.get("client_ip"),
            channel=actor_meta.get("channel"),
            entity_type=entity_type,
            entity_id=entity_id,
            operation=operation,
            status="success",
            before=safe_before,
            after=safe_after,
            metadata=_normalize_json(metadata or {}),
        )

    def record_ai_model_usage(
        self,
        *,
        objective: str | None,
        provider: str | None,
        engine: str | None,
        model_name: str | None,
        deployment_mode: str | None,
        request_kind: str,
        agent_id: str | None = None,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        total_tokens: int | None = None,
        duration_ms: float | None = None,
        tokens_per_second: float | None = None,
        success: bool = True,
        error: str | None = None,
        metadata: dict[str, Any] | None = None,
        user_id: int | None = None,
        organization_id: int | None = None,
        session_id: str | None = None,
        node_id: str | None = None,
        engine_row_id: int | None = None,
    ):
        request_meta = self._request_metadata()
        if engine_row_id is None:
            try:
                from democrai.core.application.ai.pipeline_context import (
                    current_ai_pipeline_context,
                )

                pipeline_context = current_ai_pipeline_context()
                engine_row_id = (
                    pipeline_context.engine_row_id
                    if pipeline_context is not None
                    else None
                )
            except Exception:
                engine_row_id = None
        return self._emit(
            "record_ai_model_usage",
            user_id=user_id if user_id is not None else request_meta.get("actor_user_id"),
            organization_id=organization_id if organization_id is not None else request_meta.get("organization_id"),
            session_id=session_id if session_id is not None else request_meta.get("session_id"),
            node_id=node_id if node_id is not None else _runtime_node_id(),
            request_id=request_meta.get("request_id"),
            correlation_id=request_meta.get("correlation_id"),
            client_ip=request_meta.get("client_ip"),
            channel=request_meta.get("channel"),
            objective=objective,
            provider=provider,
            engine=engine,
            engine_row_id=engine_row_id,
            model_name=model_name,
            deployment_mode=deployment_mode,
            request_kind=request_kind,
            agent_id=agent_id,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            duration_ms=duration_ms,
            tokens_per_second=tokens_per_second,
            success=success,
            error=error,
            metadata=_normalize_json(metadata or {}),
        )

    def record_ai_model_runtime(
        self,
        *,
        event_type: str,
        provider: str | None = None,
        engine: str | None = None,
        engine_row_id: int | None = None,
        model_registry_id: int | None = None,
        model_name: str | None = None,
        session_id: str | None = None,
        node_id: str | None = None,
        config_signature: str | None = None,
        warmup_ms: float | None = None,
        model_weight_vram_mb: int | None = None,
        vram_before_mb: int | None = None,
        vram_after_mb: int | None = None,
        vram_delta_mb: int | None = None,
        runtime_allocated_vram_mb: int | None = None,
        ram_before_mb: int | None = None,
        ram_after_mb: int | None = None,
        success: bool = True,
        error: str | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        request_meta = self._request_metadata()
        return self._emit(
            "record_ai_model_runtime",
            user_id=request_meta.get("actor_user_id"),
            organization_id=request_meta.get("organization_id"),
            session_id=session_id if session_id is not None else request_meta.get("session_id"),
            request_id=request_meta.get("request_id"),
            correlation_id=request_meta.get("correlation_id"),
            client_ip=request_meta.get("client_ip"),
            channel=request_meta.get("channel"),
            event_type=event_type,
            provider=provider,
            engine=engine,
            engine_row_id=engine_row_id,
            model_registry_id=model_registry_id,
            model_name=model_name,
            node_id=node_id if node_id is not None else _runtime_node_id(),
            config_signature=config_signature,
            warmup_ms=warmup_ms,
            model_weight_vram_mb=model_weight_vram_mb,
            vram_before_mb=vram_before_mb,
            vram_after_mb=vram_after_mb,
            vram_delta_mb=vram_delta_mb,
            runtime_allocated_vram_mb=runtime_allocated_vram_mb,
            ram_before_mb=ram_before_mb,
            ram_after_mb=ram_after_mb,
            success=success,
            error=error,
            metadata=_normalize_json(metadata or {}),
        )

    def record_ai_model_pipeline_step(self, **kwargs):
        payload = dict(kwargs)
        for key in ("input", "output", "stats", "metadata"):
            payload[key] = _normalize_json(payload.get(key) or {})
        archive_enabled = self._trace_archive_enabled()
        stored_payload, archive_payload = prepare_pipeline_step_record(
            payload,
            preview_chars=self._trace_preview_chars(),
            archive_enabled=archive_enabled,
        )
        event = self._emit("record_ai_model_pipeline_step", **stored_payload)
        if event is not None and archive_payload is not None:
            self._emit(
                "enqueue_trace_archive",
                pipeline_step_db_id=getattr(event, "id", None),
                pipeline_id=str(payload.get("pipeline_id") or ""),
                request_id=payload.get("request_id"),
                step_id=str(payload.get("step_id") or ""),
                payload_kind="ai_model_pipeline_step",
                payload=archive_payload,
                payload_hash=archive_queue_payload_hash(archive_payload),
            )
        return event

    def _trace_archive_enabled(self) -> bool:
        cfg = getattr(app_ctx(), "config", None)
        if cfg is None:
            return True
        return bool(cfg.get("storage.observability.traces.archive_payloads", True))

    def _trace_preview_chars(self) -> int:
        cfg = getattr(app_ctx(), "config", None)
        if cfg is None:
            return 512
        return int(cfg.get("storage.observability.traces.inline_preview_chars", 512))


observability_service = ObservabilityService()
