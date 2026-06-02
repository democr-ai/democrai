from __future__ import annotations

from typing import Any

from sqlalchemy.exc import OperationalError

from democrai.core.application.access_policy import AccessRequest
from democrai.core.application.access_policy import AccessResource
from democrai.core.application.access_policy import AccessScope
from democrai.core.application.access_policy import AccessSubject
from democrai.core.infrastructure.database import session_scope
from democrai.core.infrastructure.database.models import ExternalAccessApproval
from democrai.core.infrastructure.database.models import ExternalAccessRequest
from democrai.core.platform.utils.identity import to_optional_int
from democrai.core.platform.utils.timezone import utc_now_naive


_TERMINAL_REQUEST_STATUSES = {"session", "approved", "denied"}


def upsert_pending_access_request(
    request: AccessRequest,
    *,
    subject_chain: list[dict[str, str]] | None = None,
    resume_action: str | None = None,
    resume_context: str | None = None,
    resume_context_hash: str | None = None,
) -> bool:
    now = utc_now_naive()
    normalized_resume_action = (
        resume_action.strip() if resume_action is not None else None
    )
    if normalized_resume_action == "":
        normalized_resume_action = None
    normalized_resume_context = (
        resume_context.strip() if resume_context is not None else None
    )
    if normalized_resume_context == "":
        normalized_resume_context = None
    normalized_resume_context_hash = (
        resume_context_hash.strip() if resume_context_hash is not None else None
    )
    if normalized_resume_context_hash == "":
        normalized_resume_context_hash = None
    try:
        with session_scope() as db:
            row = _find_request_row(db, request)
            if row is None:
                db.add(
                    ExternalAccessRequest(
                        subject_type=request.subject.subject_type,
                        subject_name=request.subject.subject_name,
                        resource_type=request.resource.resource_type.value,
                        operation=request.resource.operation.value,
                        target=request.resource.target,
                        normalized_target=request.resource.normalized_target,
                        scope="pending",
                        requested_by=request.origin.requested_by,
                        subject_chain=_normalize_subject_chain(subject_chain),
                        session_key=request.origin.session_key,
                        organization_id=request.origin.organization_id,
                        task_id=request.origin.task_id,
                        resume_action=normalized_resume_action,
                        resume_context=normalized_resume_context,
                        resume_context_hash=normalized_resume_context_hash,
                        status="pending",
                        created_at=now,
                        last_requested_at=now,
                    )
                )
                db.commit()
                return True

            if row.status.strip().lower() not in _TERMINAL_REQUEST_STATUSES:
                row.status = "pending"
                row.scope = "pending"
            row.subject_chain = _normalize_subject_chain(subject_chain)
            row.session_key = request.origin.session_key
            row.organization_id = request.origin.organization_id
            row.task_id = request.origin.task_id
            row.resume_action = normalized_resume_action
            row.resume_context = normalized_resume_context
            row.resume_context_hash = normalized_resume_context_hash
            row.last_requested_at = now
            db.commit()
            return False
    except OperationalError as exc:
        raise RuntimeError("[AccessPolicy] Failed to upsert pending request") from exc


def upsert_access_approval(
    *,
    subject: AccessSubject,
    resource: AccessResource,
    scope: AccessScope,
    approved_by: int | None,
) -> None:
    now = utc_now_naive()
    try:
        with session_scope() as db:
            row = _find_approval_row(db, subject=subject, resource=resource, scope=scope)
            if row is None:
                db.add(
                    ExternalAccessApproval(
                        subject_type=subject.subject_type,
                        subject_name=subject.subject_name,
                        resource_type=resource.resource_type.value,
                        operation=resource.operation.value,
                        target=resource.target,
                        normalized_target=resource.normalized_target,
                        scope=scope.scope_type,
                        session_key=scope.session_key,
                        approved_by=to_optional_int(approved_by),
                        created_at=now,
                        updated_at=now,
                    )
                )
                db.commit()
                return
            row.target = resource.target
            row.normalized_target = resource.normalized_target
            row.approved_by = to_optional_int(approved_by)
            row.updated_at = now
            db.commit()
    except OperationalError as exc:
        raise RuntimeError("[AccessPolicy] Failed to upsert approval") from exc


def has_access_approval(
    *,
    subject: AccessSubject,
    resource: AccessResource,
    scope: AccessScope,
) -> bool:
    try:
        with session_scope() as db:
            return (
                _find_approval_row(db, subject=subject, resource=resource, scope=scope)
                is not None
            )
    except OperationalError:
        return False


def list_access_approvals() -> list[dict[str, Any]]:
    try:
        with session_scope() as db:
            rows = db.query(ExternalAccessApproval).all()
            return [
                {
                    "subject_type": row.subject_type,
                    "subject_name": row.subject_name,
                    "resource_type": row.resource_type,
                    "operation": row.operation,
                    "normalized_target": row.normalized_target,
                    "scope": row.scope,
                    "session_key": row.session_key,
                }
                for row in rows
            ]
    except OperationalError:
        return []


def mark_access_request_decision(
    request: AccessRequest,
    *,
    status: str,
    scope: AccessScope,
) -> list[dict[str, Any]]:
    normalized_status = status.strip().lower()
    if normalized_status not in {"session", "approved", "denied"}:
        raise ValueError(f"invalid_access_request_status:{normalized_status}")
    now = utc_now_naive()
    try:
        with session_scope() as db:
            rows = _matching_request_rows(db, request)
            if normalized_status == "session":
                rows = [
                    row
                    for row in rows
                    if row.session_key == scope.session_key
                ]
            payload: list[dict[str, Any]] = []
            for row in rows:
                row.status = normalized_status
                row.scope = scope.scope_type
                row.updated_at = now
                payload.append(_request_row_to_dict(row))
            db.commit()
            return payload
    except OperationalError as exc:
        raise RuntimeError("[AccessPolicy] Failed to mark request decision") from exc


def is_access_denied(*, subject: AccessSubject, resource: AccessResource) -> bool:
    try:
        with session_scope() as db:
            return (
                db.query(ExternalAccessRequest)
                .filter(
                    ExternalAccessRequest.subject_type == subject.subject_type,
                    ExternalAccessRequest.subject_name == subject.subject_name,
                    ExternalAccessRequest.resource_type == resource.resource_type.value,
                    ExternalAccessRequest.operation == resource.operation.value,
                    ExternalAccessRequest.normalized_target == resource.normalized_target,
                    ExternalAccessRequest.status == "denied",
                )
                .first()
                is not None
            )
    except OperationalError:
        return False


def list_denied_access_requests() -> list[dict[str, Any]]:
    try:
        with session_scope() as db:
            rows = (
                db.query(ExternalAccessRequest)
                .filter(ExternalAccessRequest.status == "denied")
                .all()
            )
            return [
                {
                    "subject_type": row.subject_type,
                    "subject_name": row.subject_name,
                    "resource_type": row.resource_type,
                    "operation": row.operation,
                    "normalized_target": row.normalized_target,
                }
                for row in rows
            ]
    except OperationalError:
        return []


def get_pending_access_requests() -> list[dict[str, Any]]:
    try:
        with session_scope() as db:
            rows = (
                db.query(ExternalAccessRequest)
                .filter(ExternalAccessRequest.status == "pending")
                .order_by(ExternalAccessRequest.last_requested_at.desc())
                .all()
            )
            return [_request_row_to_dict(row) for row in rows]
    except OperationalError:
        return []


def _find_request_row(db: Any, request: AccessRequest):
    return (
        db.query(ExternalAccessRequest)
        .filter(
            ExternalAccessRequest.subject_type == request.subject.subject_type,
            ExternalAccessRequest.subject_name == request.subject.subject_name,
            ExternalAccessRequest.resource_type == request.resource.resource_type.value,
            ExternalAccessRequest.operation == request.resource.operation.value,
            ExternalAccessRequest.normalized_target == request.resource.normalized_target,
            ExternalAccessRequest.requested_by == request.origin.requested_by,
            ExternalAccessRequest.session_key == request.origin.session_key,
        )
        .first()
    )


def _matching_request_rows(db: Any, request: AccessRequest) -> list[ExternalAccessRequest]:
    return (
        db.query(ExternalAccessRequest)
        .filter(
            ExternalAccessRequest.subject_type == request.subject.subject_type,
            ExternalAccessRequest.subject_name == request.subject.subject_name,
            ExternalAccessRequest.resource_type == request.resource.resource_type.value,
            ExternalAccessRequest.operation == request.resource.operation.value,
            ExternalAccessRequest.normalized_target == request.resource.normalized_target,
        )
        .all()
    )


def _find_approval_row(
    db: Any,
    *,
    subject: AccessSubject,
    resource: AccessResource,
    scope: AccessScope,
):
    return (
        db.query(ExternalAccessApproval)
        .filter(
            ExternalAccessApproval.subject_type == subject.subject_type,
            ExternalAccessApproval.subject_name == subject.subject_name,
            ExternalAccessApproval.resource_type == resource.resource_type.value,
            ExternalAccessApproval.operation == resource.operation.value,
            ExternalAccessApproval.normalized_target == resource.normalized_target,
            ExternalAccessApproval.scope == scope.scope_type,
            ExternalAccessApproval.session_key == scope.session_key,
        )
        .first()
    )


def _normalize_subject_chain(
    subject_chain: list[dict[str, str]] | None,
) -> list[dict[str, str]] | None:
    if subject_chain is None:
        return None
    normalized: list[dict[str, str]] = []
    for item in subject_chain:
        kind = item["kind"].strip().lower()
        name = item["name"].strip()
        if not kind or not name:
            raise ValueError("invalid_access_subject_chain_entry")
        normalized.append({"kind": kind, "name": name})
    if not normalized:
        return None
    return normalized


def _request_row_to_dict(row: ExternalAccessRequest) -> dict[str, Any]:
    return {
        "id": getattr(row, "id", None),
        "subject_type": getattr(row, "subject_type", None),
        "subject_name": getattr(row, "subject_name", None),
        "resource_type": getattr(row, "resource_type", None),
        "operation": getattr(row, "operation", None),
        "target": getattr(row, "target", None),
        "normalized_target": getattr(row, "normalized_target", None),
        "scope": getattr(row, "scope", None),
        "requested_by": getattr(row, "requested_by", None),
        "organization_id": getattr(row, "organization_id", None),
        "session_key": getattr(row, "session_key", None),
        "task_id": getattr(row, "task_id", None),
        "subject_chain": getattr(row, "subject_chain", None),
        "resume_action": getattr(row, "resume_action", None),
        "resume_context": getattr(row, "resume_context", None),
        "resume_context_hash": getattr(row, "resume_context_hash", None),
        "status": getattr(row, "status", None),
        "created_at": getattr(row, "created_at", None),
        "last_requested_at": getattr(row, "last_requested_at", None),
    }
