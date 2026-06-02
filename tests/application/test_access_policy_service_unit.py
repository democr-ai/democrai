from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from democrai.core.application.access_policy import AccessPolicyService
from democrai.core.application.access_policy import AccessRequest
from democrai.core.application.access_policy import AccessScope
from democrai.core.application.access_policy.keys import access_fingerprint


@dataclass
class _Repo:
    approvals: set[str] = field(default_factory=set)
    denied: set[str] = field(default_factory=set)
    pending: list[dict] = field(default_factory=list)
    marked: list[dict] = field(default_factory=list)

    def _key(self, request_or_subject=None, *, subject=None, resource=None, scope=None):
        if request_or_subject is not None:
            subject = request_or_subject.subject
            resource = request_or_subject.resource
        return access_fingerprint(
            subject=subject,
            resource=resource,
            scope=getattr(scope, "scope_type", None),
            session_key=getattr(scope, "session_key", None),
        )

    def upsert_pending_access_request(self, request, **kwargs):
        self.pending.append({"request": request, **kwargs})
        return True

    def has_access_approval(self, *, subject, resource, scope):
        return self._key(subject=subject, resource=resource, scope=scope) in self.approvals

    def upsert_access_approval(self, *, subject, resource, scope, approved_by):
        self.approvals.add(self._key(subject=subject, resource=resource, scope=scope))

    def mark_access_request_decision(self, request, *, status, scope):
        row = {
            "status": status,
            "scope": scope.scope_type,
            "session_key": scope.session_key,
            "operation": request.resource.operation.value,
        }
        self.marked.append(row)
        if status == "denied":
            self.denied.add(self._key(request))
        return [row]

    def is_access_denied(self, *, subject, resource):
        permanent_key = access_fingerprint(
            subject=subject,
            resource=resource,
        )
        return permanent_key in self.denied


def _request(*, session_key: str | None = "sess-1") -> AccessRequest:
    return AccessRequest.create(
        subject_type="module",
        subject_name="system",
        resource_type="network",
        operation="receive",
        target="https://api.example.com",
        requested_by=1,
        session_key=session_key,
    )


def test_access_policy_service_registers_pending_when_not_approved():
    repo = _Repo()
    service = AccessPolicyService(repo)
    request = _request()

    decision = service.check_access(
        request,
        subject_chain=[{"kind": "module", "name": "system"}],
        resume_action="system.resume",
        resume_context="encrypted",
        resume_context_hash="hash",
    )

    assert decision.allowed is False
    assert decision.requires_approval is True
    assert decision.code == "not_enabled"
    assert len(repo.pending) == 1
    assert repo.pending[0]["resume_action"] == "system.resume"


def test_access_policy_service_allows_permanent_approval_without_pending():
    repo = _Repo()
    service = AccessPolicyService(repo)
    request = _request()
    repo.upsert_access_approval(
        subject=request.subject,
        resource=request.resource,
        scope=AccessScope.permanent(),
        approved_by=1,
    )

    decision = service.check_access(request)

    assert decision.allowed is True
    assert decision.code == "permanent_approval"
    assert repo.pending == []


def test_access_policy_service_allows_session_approval_only_for_same_session():
    repo = _Repo()
    service = AccessPolicyService(repo)
    request = _request(session_key="sess-1")
    repo.upsert_access_approval(
        subject=request.subject,
        resource=request.resource,
        scope=AccessScope.session("sess-1"),
        approved_by=1,
    )

    assert service.check_access(request).allowed is True
    assert service.check_access(_request(session_key="sess-2")).allowed is False


def test_access_policy_service_approve_and_deny_mark_requests():
    repo = _Repo()
    service = AccessPolicyService(repo)
    request = _request()

    permanent_rows = service.approve_permanently(request, approved_by=1)
    session_rows = service.approve_for_session(request, approved_by=1)
    denied_rows = service.deny(request)

    assert permanent_rows[0]["status"] == "approved"
    assert session_rows[0]["status"] == "session"
    assert denied_rows[0]["status"] == "denied"


def test_access_policy_service_session_approval_requires_session():
    service = AccessPolicyService(_Repo())
    with pytest.raises(PermissionError, match="access_policy_session_key_required"):
        service.approve_for_session(_request(session_key=None), approved_by=1)
