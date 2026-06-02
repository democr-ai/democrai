from __future__ import annotations

import os
from typing import Any

from democrai.core.application.environment.crypto import decrypt_value
from democrai.core.application.environment.crypto import encrypt_value
from democrai.core.application.environment.definitions import list_environment_definitions
from democrai.core.application.environment.definitions import verify_env_name
from democrai.core.application.environment.definitions import verify_subject
from democrai.core.application.environment.definitions import verify_subject_kind
from democrai.core.infrastructure.database import SessionLocal
from democrai.core.infrastructure.database.models import EnvironmentVariableRegistry
from democrai.core.infrastructure.sandbox.process_guard import process_guard_bypass_context
from democrai.core.platform.utils.timezone import utc_now_naive


def _mask(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "********"
    return f"{value[:4]}...{value[-4:]}"


def _row_to_dict(row: EnvironmentVariableRegistry) -> dict[str, Any]:
    plain = decrypt_value(row.value_encrypted)
    row_key = f"{row.subject_kind}:{row.subject}:{row.name}"
    return {
        "id": row.id,
        "row_key": row_key,
        "subject_kind": row.subject_kind,
        "subject": row.subject,
        "name": row.name,
        "enabled": row.enabled,
        "has_value": plain != "",
        "masked_value": _mask(plain),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _find_row(session, *, subject_kind: str, subject: str, name: str):
    return (
        session.query(EnvironmentVariableRegistry)
        .filter(
            EnvironmentVariableRegistry.subject_kind == subject_kind,
            EnvironmentVariableRegistry.subject == subject,
            EnvironmentVariableRegistry.name == name,
        )
        .first()
    )


def _set_process_env(name: str, value: str) -> None:
    with process_guard_bypass_context():
        os.environ[name] = value


def _unset_process_env(name: str) -> None:
    with process_guard_bypass_context():
        os.environ.pop(name, None)


def _apply_name_from_rows(name: str, rows: list[EnvironmentVariableRegistry]) -> None:
    active_rows = [
        row
        for row in rows
        if row.enabled and decrypt_value(row.value_encrypted)
    ]
    if not active_rows:
        _unset_process_env(name)
        return
    active_rows.sort(
        key=lambda row: (
            row.updated_at or row.created_at,
            row.id,
        ),
        reverse=True,
    )
    _set_process_env(name, decrypt_value(active_rows[0].value_encrypted))


def apply_environment_variables(
    *,
    subject_kind: str | None = None,
    subject: str | None = None,
    name: str | None = None,
) -> int:
    kind = verify_subject_kind(subject_kind) if subject_kind is not None else None
    resolved_subject = verify_subject(subject) if subject is not None else None
    resolved_name = verify_env_name(name) if name is not None else None
    with SessionLocal() as session:
        query = session.query(EnvironmentVariableRegistry)
        if kind:
            query = query.filter(EnvironmentVariableRegistry.subject_kind == kind)
        if resolved_subject:
            query = query.filter(EnvironmentVariableRegistry.subject == resolved_subject)
        if resolved_name:
            query = query.filter(EnvironmentVariableRegistry.name == resolved_name)
        rows = query.all()
        if resolved_name:
            _apply_name_from_rows(resolved_name, rows)
            return len(rows)
        grouped: dict[str, list[EnvironmentVariableRegistry]] = {}
        for row in rows:
            grouped.setdefault(row.name, []).append(row)
        for env_name, env_rows in grouped.items():
            _apply_name_from_rows(env_name, env_rows)
        return len(rows)


def list_environment_variables(
    *,
    subject_kind: str | None = None,
    subject: str | None = None,
) -> list[dict[str, Any]]:
    kind = verify_subject_kind(subject_kind) if subject_kind is not None else None
    resolved_subject = verify_subject(subject) if subject is not None else None
    definitions = {
        (item["subject_kind"], item["subject"], item["name"]): item
        for item in list_environment_definitions(
            subject_kind=kind or None,
            subject=resolved_subject or None,
        )
    }
    with SessionLocal() as session:
        query = session.query(EnvironmentVariableRegistry)
        if kind:
            query = query.filter(EnvironmentVariableRegistry.subject_kind == kind)
        if resolved_subject:
            query = query.filter(EnvironmentVariableRegistry.subject == resolved_subject)
        rows = query.all()

    merged: dict[tuple[str, str, str], dict[str, Any]] = {}
    for key, definition in definitions.items():
        subject_kind, subject, name = key
        merged[key] = {
            **definition,
            "id": None,
            "row_key": f"{subject_kind}:{subject}:{name}",
            "enabled": False,
            "has_value": False,
            "masked_value": "",
            "configured": False,
            "source": "manifest",
        }
    for row in rows:
        item = _row_to_dict(row)
        key = (item["subject_kind"], item["subject"], item["name"])
        if key not in definitions:
            continue
        definition = definitions.get(key, {})
        merged[key] = {
            **definition,
            **item,
            "label": definition["label"],
            "description": definition["description"],
            "required": definition["required"],
            "secret": definition["secret"],
            "configured": True,
            "source": "database",
        }
    output = list(merged.values())
    output.sort(key=lambda item: (item["subject_kind"], item["subject"], item["name"]))
    return output


async def set_environment_variable(
    *,
    subject_kind: str,
    subject: str,
    name: str,
    value: str | None,
    enabled: bool = True,
    dispatch: bool = True,
) -> dict[str, Any]:
    if not isinstance(enabled, bool):
        raise ValueError("invalid_environment_variable_enabled")
    kind = verify_subject_kind(subject_kind)
    resolved_subject = verify_subject(subject)
    resolved_name = verify_env_name(name)
    definition_key = (kind, resolved_subject, resolved_name)
    definitions = {
        (item["subject_kind"], item["subject"], item["name"])
        for item in list_environment_definitions(subject_kind=kind, subject=resolved_subject)
    }
    if definition_key not in definitions:
        raise ValueError("environment_variable_definition_not_found")
    with SessionLocal() as session:
        row = _find_row(
            session,
            subject_kind=kind,
            subject=resolved_subject,
            name=resolved_name,
        )
        now = utc_now_naive()
        if row is None:
            if value is None:
                raise ValueError("environment_variable_value_required")
            row = EnvironmentVariableRegistry(
                subject_kind=kind,
                subject=resolved_subject,
                name=resolved_name,
                value_encrypted=encrypt_value(value),
                enabled=enabled,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
        else:
            if value is not None:
                row.value_encrypted = encrypt_value(value)
            row.enabled = enabled
            row.updated_at = now
        session.commit()
        session.refresh(row)
        result = _row_to_dict(row)
    apply_environment_variables(name=resolved_name)

    if dispatch:
        from democrai.core.application.environment.events import publish_environment_changed

        await publish_environment_changed(
            operation="set",
            subject_kind=kind,
            subject=resolved_subject,
            name=resolved_name,
        )
    return result


async def delete_environment_variable(
    *,
    variable_id: int | None = None,
    subject_kind: str | None = None,
    subject: str | None = None,
    name: str | None = None,
    dispatch: bool = True,
) -> bool:
    deleted: dict[str, str] | None = None
    with SessionLocal() as session:
        row = None
        if variable_id is not None:
            if not isinstance(variable_id, int):
                raise ValueError("invalid_environment_variable_id")
            row = (
                session.query(EnvironmentVariableRegistry)
                .filter(EnvironmentVariableRegistry.id == variable_id)
                .first()
            )
        elif subject_kind and name:
            row = _find_row(
                session,
                subject_kind=verify_subject_kind(subject_kind),
                subject=verify_subject("" if subject is None else subject),
                name=verify_env_name(name),
            )
        if row is None:
            return False
        deleted = {
            "subject_kind": row.subject_kind,
            "subject": row.subject,
            "name": row.name,
        }
        session.delete(row)
        session.commit()
    apply_environment_variables(name=deleted["name"])
    if dispatch:
        from democrai.core.application.environment.events import publish_environment_changed

        await publish_environment_changed(operation="delete", **deleted)
    return True
