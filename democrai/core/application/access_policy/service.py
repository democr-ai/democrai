from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from democrai.core.application.access_policy.models import AccessDecision
from democrai.core.application.access_policy.models import AccessRequest
from democrai.core.application.access_policy.models import AccessResource
from democrai.core.application.access_policy.models import AccessScope
from democrai.core.application.access_policy.models import AccessSubject


class AccessPolicyRepository(Protocol):
    def upsert_pending_access_request(
        self,
        request: AccessRequest,
        *,
        subject_chain: list[dict[str, str]] | None = None,
        resume_action: str | None = None,
        resume_context: str | None = None,
        resume_context_hash: str | None = None,
    ) -> bool:
        ...

    def has_access_approval(
        self,
        *,
        subject: AccessSubject,
        resource: AccessResource,
        scope: AccessScope,
    ) -> bool:
        ...

    def upsert_access_approval(
        self,
        *,
        subject: AccessSubject,
        resource: AccessResource,
        scope: AccessScope,
        approved_by: int | None,
    ) -> None:
        ...

    def mark_access_request_decision(
        self,
        request: AccessRequest,
        *,
        status: str,
        scope: AccessScope,
    ) -> list[dict]:
        ...

    def is_access_denied(
        self,
        *,
        subject: AccessSubject,
        resource: AccessResource,
    ) -> bool:
        ...


@dataclass(frozen=True, slots=True)
class AccessPolicyService:
    repository: AccessPolicyRepository

    def check_access(
        self,
        request: AccessRequest,
        *,
        register_request: bool = True,
        subject_chain: list[dict[str, str]] | None = None,
        resume_action: str | None = None,
        resume_context: str | None = None,
        resume_context_hash: str | None = None,
    ) -> AccessDecision:
        permanent_scope = AccessScope.permanent()
        if self.repository.has_access_approval(
            subject=request.subject,
            resource=request.resource,
            scope=permanent_scope,
        ):
            return AccessDecision.allow(
                "permanent_approval",
                "Access enabled by permanent approval.",
            )

        if request.origin.session_key:
            session_scope = AccessScope.session(request.origin.session_key)
            if self.repository.has_access_approval(
                subject=request.subject,
                resource=request.resource,
                scope=session_scope,
            ):
                return AccessDecision.allow(
                    "session_approval",
                    "Access enabled for current session.",
                )

        if self.repository.is_access_denied(
            subject=request.subject,
            resource=request.resource,
        ):
            return AccessDecision.deny(
                "denied",
                "Access denied.",
            )

        if register_request:
            self.repository.upsert_pending_access_request(
                request,
                subject_chain=subject_chain,
                resume_action=resume_action,
                resume_context=resume_context,
                resume_context_hash=resume_context_hash,
            )

        return AccessDecision.require_approval(
            "not_enabled",
            "Access requires approval.",
        )

    def approve_permanently(
        self,
        request: AccessRequest,
        *,
        approved_by: int | None,
    ) -> list[dict]:
        scope = AccessScope.permanent()
        self.repository.upsert_access_approval(
            subject=request.subject,
            resource=request.resource,
            scope=scope,
            approved_by=approved_by,
        )
        return self.repository.mark_access_request_decision(
            request,
            status="approved",
            scope=scope,
        )

    def approve_for_session(
        self,
        request: AccessRequest,
        *,
        approved_by: int | None,
        session_key: str | None = None,
    ) -> list[dict]:
        resolved_session_key = str(session_key or request.origin.session_key or "").strip()
        if not resolved_session_key:
            raise PermissionError("access_policy_session_key_required")
        scope = AccessScope.session(resolved_session_key)
        self.repository.upsert_access_approval(
            subject=request.subject,
            resource=request.resource,
            scope=scope,
            approved_by=approved_by,
        )
        rows = self.repository.mark_access_request_decision(
            request,
            status="session",
            scope=scope,
        )
        if not rows:
            raise PermissionError("access_policy_session_request_not_found")
        return rows

    def deny(self, request: AccessRequest) -> list[dict]:
        return self.repository.mark_access_request_decision(
            request,
            status="denied",
            scope=AccessScope.pending(request.origin.session_key),
        )
