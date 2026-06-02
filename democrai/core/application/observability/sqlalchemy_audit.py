from __future__ import annotations

from typing import Any

from sqlalchemy import event
from sqlalchemy.orm import Session

from democrai.core.application.observability.service import observability_service
from democrai.core.application.observability.service import resolve_entity_identity
from democrai.core.application.observability.service import snapshot_model
from democrai.core.application.observability.service import snapshot_model_before_update


_AUDIT_ENTRIES_KEY = "_observability_audit_entries"
_AUDIT_INSTALLED = False

_AUDIT_EXCLUDED_TABLES = {
    "runtime_node_registry",
}


def _is_observability_table(obj: Any) -> bool:
    table_name = getattr(obj, "__tablename__", "") or ""
    return table_name in {
        "events",
        "audit_events",
        "ai_model_usage_events",
        "ai_model_runtime_events",
    }


def _is_auditable(obj: Any) -> bool:
    table_name = getattr(obj, "__tablename__", "") or ""
    if table_name in _AUDIT_EXCLUDED_TABLES:
        return False
    if _is_observability_table(obj):
        return False
    if not hasattr(obj, "__table__"):
        return False
    return True


def _actor_metadata(session: Session) -> dict[str, Any]:
    return dict(session.info.get("observability_actor") or {})


def _audit_compact_fields(obj: Any) -> set[str]:
    fields = getattr(obj, "__audit_compact_fields__", set()) or set()
    return {field for field in fields if field}


def install_sqlalchemy_audit_hooks() -> None:
    global _AUDIT_INSTALLED
    if _AUDIT_INSTALLED:
        return
    _AUDIT_INSTALLED = True

    @event.listens_for(Session, "before_flush")
    def _capture_changes(session: Session, flush_context, instances) -> None:
        _ = (flush_context, instances)
        if session.info.get("skip_observability_audit"):
            return
        entries = session.info.setdefault(_AUDIT_ENTRIES_KEY, [])
        seen = session.info.setdefault(f"{_AUDIT_ENTRIES_KEY}_seen", set())

        for obj in list(session.new):
            if not _is_auditable(obj):
                continue
            identity_key = ("insert", id(obj))
            if identity_key in seen:
                continue
            seen.add(identity_key)
            entries.append(
                {
                    "operation": "insert",
                    "obj": obj,
                    "entity_type": resolve_entity_identity(obj)[0],
                    "entity_id": None,
                    "before": {},
                    "after": None,
                    "compact_fields": _audit_compact_fields(obj),
                    "actor": _actor_metadata(session),
                }
            )

        for obj in list(session.dirty):
            if not _is_auditable(obj) or not session.is_modified(
                obj, include_collections=False
            ):
                continue
            entity_type, entity_id = resolve_entity_identity(obj)
            identity_key = ("update", entity_type, entity_id, id(obj))
            if identity_key in seen:
                continue
            seen.add(identity_key)
            entries.append(
                {
                    "operation": "update",
                    "obj": None,
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "before": snapshot_model_before_update(obj),
                    "after": snapshot_model(obj),
                    "compact_fields": _audit_compact_fields(obj),
                    "actor": _actor_metadata(session),
                }
            )

        for obj in list(session.deleted):
            if not _is_auditable(obj):
                continue
            entity_type, entity_id = resolve_entity_identity(obj)
            identity_key = ("delete", entity_type, entity_id, id(obj))
            if identity_key in seen:
                continue
            seen.add(identity_key)
            entries.append(
                {
                    "operation": "delete",
                    "obj": None,
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "before": snapshot_model(obj),
                    "after": {},
                    "compact_fields": _audit_compact_fields(obj),
                    "actor": _actor_metadata(session),
                }
            )

    @event.listens_for(Session, "after_flush_postexec")
    def _finalize_inserts(session: Session, flush_context) -> None:
        _ = flush_context
        if session.info.get("skip_observability_audit"):
            return
        for entry in session.info.get(_AUDIT_ENTRIES_KEY, []):
            if entry.get("operation") != "insert" or entry.get("obj") is None:
                continue
            obj = entry["obj"]
            entry["entity_type"], entry["entity_id"] = resolve_entity_identity(obj)
            entry["after"] = snapshot_model(obj)
            entry["obj"] = None

    @event.listens_for(Session, "after_commit")
    def _emit_changes(session: Session) -> None:
        if session.info.get("skip_observability_audit"):
            session.info.pop(_AUDIT_ENTRIES_KEY, None)
            session.info.pop(f"{_AUDIT_ENTRIES_KEY}_seen", None)
            return
        entries = session.info.pop(_AUDIT_ENTRIES_KEY, [])
        session.info.pop(f"{_AUDIT_ENTRIES_KEY}_seen", None)
        for entry in entries:
            observability_service.record_db_mutation(
                operation=entry["operation"],
                entity_type=entry.get("entity_type"),
                entity_id=entry.get("entity_id"),
                before=entry.get("before"),
                after=entry.get("after"),
                metadata={},
                actor=entry.get("actor"),
                compact_fields=entry.get("compact_fields"),
            )

    @event.listens_for(Session, "after_rollback")
    def _clear_changes(session: Session) -> None:
        session.info.pop(_AUDIT_ENTRIES_KEY, None)
        session.info.pop(f"{_AUDIT_ENTRIES_KEY}_seen", None)
