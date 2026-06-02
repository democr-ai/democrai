from __future__ import annotations

import hashlib
import json

from democrai.core.application.access_policy.models import AccessRequest
from democrai.core.application.access_policy.models import AccessResource
from democrai.core.application.access_policy.models import AccessSubject


def access_fingerprint(
    *,
    subject: AccessSubject,
    resource: AccessResource,
    scope: str | None = None,
    session_key: str | None = None,
) -> str:
    payload = {
        "subject_type": subject.subject_type,
        "subject_name": subject.subject_name,
        "resource_type": resource.resource_type.value,
        "operation": resource.operation.value,
        "normalized_target": resource.normalized_target,
        "scope": scope or None,
        "session_key": session_key or None,
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def request_fingerprint(
    request: AccessRequest,
    *,
    scope: str | None = None,
) -> str:
    return access_fingerprint(
        subject=request.subject,
        resource=request.resource,
        scope=scope,
        session_key=request.origin.session_key,
    )
