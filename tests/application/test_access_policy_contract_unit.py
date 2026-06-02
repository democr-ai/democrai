from __future__ import annotations

from pathlib import Path

import pytest

from democrai.core.application.access_policy import AccessOperation
from democrai.core.application.access_policy import AccessDecision
from democrai.core.application.access_policy import AccessRequest
from democrai.core.application.access_policy import AccessResource
from democrai.core.application.access_policy import AccessScope
from democrai.core.application.access_policy import AccessSubject
from democrai.core.application.access_policy import AccessSubjectType
from democrai.core.application.access_policy import ResourceType
from democrai.core.application.access_policy import access_fingerprint
from democrai.core.application.access_policy import normalize_network_target
from democrai.core.application.access_policy import normalize_target
from democrai.core.application.access_policy import operation_for_http_method
from democrai.core.application.access_policy import request_fingerprint
from democrai.core.application.access_policy import validate_operation_for_resource
from democrai.core.application.access_policy import verify_resource_type
from democrai.core.application.access_policy import verify_subject_type


def test_access_policy_verifies_subject_resource_and_operation():
    assert verify_subject_type("engine") == AccessSubjectType.ENGINE
    assert verify_resource_type("url") == ResourceType.NETWORK
    assert verify_resource_type("filesystem") == ResourceType.FILESYSTEM
    assert operation_for_http_method("GET") == AccessOperation.RECEIVE
    assert operation_for_http_method("post") == AccessOperation.SEND
    assert validate_operation_for_resource("network", "connect") == AccessOperation.CONNECT
    assert validate_operation_for_resource("filesystem", "delete") == AccessOperation.DELETE

    with pytest.raises(ValueError, match="invalid_access_operation_for_resource"):
        validate_operation_for_resource("network", "delete")
    with pytest.raises(ValueError, match="invalid_access_operation_for_resource"):
        validate_operation_for_resource("filesystem", "send")
    with pytest.raises(ValueError, match="unsupported_access_subject_type"):
        verify_subject_type("unknown")
    with pytest.raises(ValueError, match="unsupported_access_subject_type"):
        verify_subject_type(" Engine ")
    with pytest.raises(ValueError, match="unsupported_access_resource_type"):
        verify_resource_type(" filesystem ")


def test_access_policy_normalizes_targets(tmp_path: Path):
    path = tmp_path / "folder" / ".." / "model.bin"
    normalized_path = normalize_target("filesystem", str(path))
    assert normalized_path.endswith("model.bin")
    assert normalized_path == str(path.resolve())

    assert (
        normalize_network_target("HTTPS://Example.COM/a?b=1#F")
        == "https://Example.COM/a?b=1#F"
    )
    assert normalize_network_target("ssh://Host:22/path") == "ssh://Host:22"
    assert normalize_network_target("Example.COM:443") == "example.com:443"


def test_access_policy_request_dto_is_structured():
    request = AccessRequest.create(
        subject_type="engine",
        subject_name="whisper",
        resource_type="network",
        operation="receive",
        target="HTTPS://huggingface.co/openai/whisper",
        requested_by="12",
        organization_id=None,
        session_key=" sess-1 ",
        task_id=" task-9 ",
    )

    assert request.subject.subject_type == "engine"
    assert request.subject.subject_name == "whisper"
    assert request.resource.resource_type == ResourceType.NETWORK
    assert request.resource.operation == AccessOperation.RECEIVE
    assert request.resource.normalized_target == "https://huggingface.co/openai/whisper"
    assert request.origin.requested_by == "12"
    assert request.origin.session_key == " sess-1 "
    assert request.origin.task_id == " task-9 "
    assert request.to_dict()["resource"]["operation"] == "receive"


def test_access_policy_scope_and_decision_are_structured():
    session_scope = AccessScope.session(" sess-1 ")
    permanent_scope = AccessScope.permanent()
    pending_scope = AccessScope.pending()

    assert session_scope.to_dict() == {
        "scope_type": "session",
        "session_key": " sess-1 ",
    }
    assert permanent_scope.to_dict() == {
        "scope_type": "permanent",
        "session_key": None,
    }
    assert pending_scope.to_dict() == {
        "scope_type": "pending",
        "session_key": None,
    }
    with pytest.raises(ValueError, match="access_scope_session_key_required"):
        AccessScope.session("")

    assert AccessDecision.allow("manifest").to_dict()["allowed"] is True
    blocked = AccessDecision.require_approval("not_enabled", "External URL is locked.")
    assert blocked.allowed is False
    assert blocked.requires_approval is True
    denied = AccessDecision.deny("denied", "Denied.")
    assert denied.allowed is False
    assert denied.requires_approval is False


def test_access_policy_fingerprint_separates_operation_subject_and_session():
    subject = AccessSubject.create("module", "system")
    read_resource = AccessResource.create(
        resource_type="filesystem",
        operation="read",
        target="/tmp/demo",
    )
    delete_resource = AccessResource.create(
        resource_type="filesystem",
        operation="delete",
        target="/tmp/demo",
    )

    read_key = access_fingerprint(
        subject=subject,
        resource=read_resource,
        scope="session",
        session_key="s1",
    )
    delete_key = access_fingerprint(
        subject=subject,
        resource=delete_resource,
        scope="session",
        session_key="s1",
    )
    other_session_key = access_fingerprint(
        subject=subject,
        resource=read_resource,
        scope="session",
        session_key="s2",
    )
    other_subject_key = access_fingerprint(
        subject=AccessSubject.create("engine", "system"),
        resource=read_resource,
        scope="session",
        session_key="s1",
    )

    assert len(read_key) == 64
    assert read_key != delete_key
    assert read_key != other_session_key
    assert read_key != other_subject_key


def test_access_policy_request_fingerprint_uses_origin_session():
    first = AccessRequest.create(
        subject_type="agent",
        subject_name="planner",
        resource_type="network",
        operation="send",
        target="https://api.example.com/v1/messages",
        session_key="s1",
    )
    second = AccessRequest.create(
        subject_type="agent",
        subject_name="planner",
        resource_type="network",
        operation="send",
        target="https://api.example.com/v1/messages",
        session_key="s2",
    )

    assert request_fingerprint(first, scope="session") != request_fingerprint(
        second,
        scope="session",
    )
