from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from democrai.core.application.access_policy.operations import AccessOperation
from democrai.core.application.access_policy.operations import ResourceType
from democrai.core.application.access_policy.operations import verify_resource_type
from democrai.core.application.access_policy.operations import (
    validate_operation_for_resource,
)
from democrai.core.application.access_policy.targets import normalize_target


class AccessSubjectType:
    MODULE = "module"
    ENGINE = "engine"
    EXTRACTOR = "extractor"
    AGENT = "agent"
    TOOL = "tool"
    SKILL = "skill"
    PIPELINE = "pipeline"
    MCP = "mcp"
    CORE = "core"


_SUBJECT_TYPES = {
    AccessSubjectType.MODULE,
    AccessSubjectType.ENGINE,
    AccessSubjectType.EXTRACTOR,
    AccessSubjectType.AGENT,
    AccessSubjectType.TOOL,
    AccessSubjectType.SKILL,
    AccessSubjectType.PIPELINE,
    AccessSubjectType.MCP,
    AccessSubjectType.CORE,
}


@dataclass(frozen=True, slots=True)
class AccessSubject:
    subject_type: str
    subject_name: str

    @classmethod
    def create(cls, subject_type: str, subject_name: str) -> "AccessSubject":
        resolved_type = verify_subject_type(subject_type)
        resolved_name = subject_name
        if not resolved_name:
            raise ValueError("access_subject_name_required")
        return cls(subject_type=resolved_type, subject_name=resolved_name)

    def to_dict(self) -> dict[str, str]:
        return {
            "subject_type": self.subject_type,
            "subject_name": self.subject_name,
        }


@dataclass(frozen=True, slots=True)
class AccessResource:
    resource_type: ResourceType
    operation: AccessOperation
    target: str
    normalized_target: str

    @classmethod
    def create(
        cls,
        *,
        resource_type: str | ResourceType,
        operation: str | AccessOperation,
        target: str,
    ) -> "AccessResource":
        resolved_resource_type = verify_resource_type(resource_type)
        resolved_operation = validate_operation_for_resource(
            resolved_resource_type,
            operation,
        )
        normalized_target = normalize_target(resolved_resource_type, target)
        if not normalized_target:
            raise ValueError("access_resource_target_required")
        return cls(
            resource_type=resolved_resource_type,
            operation=resolved_operation,
            target=target,
            normalized_target=normalized_target,
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "resource_type": self.resource_type.value,
            "operation": self.operation.value,
            "target": self.target,
            "normalized_target": self.normalized_target,
        }


@dataclass(frozen=True, slots=True)
class AccessOrigin:
    requested_by: int | None = None
    organization_id: int | None = None
    session_key: str | None = None
    task_id: str | None = None

    @classmethod
    def create(
        cls,
        *,
        requested_by: int | None = None,
        organization_id: int | None = None,
        session_key: str | None = None,
        task_id: str | None = None,
    ) -> "AccessOrigin":
        return cls(
            requested_by=requested_by,
            organization_id=organization_id,
            session_key=session_key,
            task_id=task_id,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "requested_by": self.requested_by,
            "organization_id": self.organization_id,
            "session_key": self.session_key,
            "task_id": self.task_id,
        }


@dataclass(frozen=True, slots=True)
class AccessScope:
    scope_type: str
    session_key: str | None = None

    @classmethod
    def session(cls, session_key: str) -> "AccessScope":
        resolved = session_key
        if not resolved:
            raise ValueError("access_scope_session_key_required")
        return cls(scope_type="session", session_key=resolved)

    @classmethod
    def permanent(cls) -> "AccessScope":
        return cls(scope_type="permanent", session_key=None)

    @classmethod
    def pending(cls, session_key: str | None = None) -> "AccessScope":
        return cls(
            scope_type="pending",
            session_key=session_key,
        )

    def to_dict(self) -> dict[str, str | None]:
        return {
            "scope_type": self.scope_type,
            "session_key": self.session_key,
        }


@dataclass(frozen=True, slots=True)
class AccessDecision:
    allowed: bool
    requires_approval: bool
    code: str
    message: str

    @classmethod
    def allow(cls, code: str, message: str = "") -> "AccessDecision":
        return cls(
            allowed=True,
            requires_approval=False,
            code=code.strip(),
            message=message.strip(),
        )

    @classmethod
    def require_approval(cls, code: str, message: str) -> "AccessDecision":
        return cls(
            allowed=False,
            requires_approval=True,
            code=code.strip(),
            message=message.strip(),
        )

    @classmethod
    def deny(cls, code: str, message: str) -> "AccessDecision":
        return cls(
            allowed=False,
            requires_approval=False,
            code=code.strip(),
            message=message.strip(),
        )

    def to_dict(self) -> dict[str, str | bool]:
        return {
            "allowed": self.allowed,
            "requires_approval": self.requires_approval,
            "code": self.code,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class AccessRequest:
    subject: AccessSubject
    resource: AccessResource
    origin: AccessOrigin

    @classmethod
    def create(
        cls,
        *,
        subject_type: str,
        subject_name: str,
        resource_type: str | ResourceType,
        operation: str | AccessOperation,
        target: str,
        requested_by: int | None = None,
        organization_id: int | None = None,
        session_key: str | None = None,
        task_id: str | None = None,
    ) -> "AccessRequest":
        return cls(
            subject=AccessSubject.create(subject_type, subject_name),
            resource=AccessResource.create(
                resource_type=resource_type,
                operation=operation,
                target=target,
            ),
            origin=AccessOrigin.create(
                requested_by=requested_by,
                organization_id=organization_id,
                session_key=session_key,
                task_id=task_id,
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject": self.subject.to_dict(),
            "resource": self.resource.to_dict(),
            "origin": self.origin.to_dict(),
        }


def verify_subject_type(value: str) -> str:
    if value not in _SUBJECT_TYPES:
        raise ValueError(f"unsupported_access_subject_type:{value}")
    return value
