from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from democrai.core.application.access_policy.models import AccessResource
from democrai.core.application.access_policy.models import AccessSubject


@dataclass(frozen=True, slots=True)
class AccessManifestRule:
    subject: AccessSubject
    resource: AccessResource

    def to_dict(self) -> dict[str, dict[str, str]]:
        return {
            "subject": self.subject.to_dict(),
            "resource": self.resource.to_dict(),
        }


def parse_access_manifest_rules(
    manifest: dict[str, Any],
    *,
    subject_type: str,
    subject_name: str,
) -> tuple[AccessManifestRule, ...]:
    if not isinstance(manifest, dict):
        raise TypeError("access_manifest_must_be_dict")
    subject = AccessSubject.create(subject_type, subject_name)
    raw_rules = manifest.get("access")
    if raw_rules is None:
        return ()
    if not isinstance(raw_rules, list):
        raise TypeError("access_manifest_access_must_be_list")

    rules: list[AccessManifestRule] = []
    for index, item in enumerate(raw_rules):
        if not isinstance(item, dict):
            raise TypeError(f"access_manifest_rule_must_be_dict:{index}")
        resource_type = _required_string(item, "resource_type", index)
        operation = _required_string(item, "operation", index)
        target = _required_string(item, "target", index)
        rules.append(
            AccessManifestRule(
                subject=subject,
                resource=AccessResource.create(
                    resource_type=resource_type,
                    operation=operation,
                    target=target,
                ),
            )
        )
    return tuple(rules)


def _required_string(item: dict[str, Any], key: str, index: int) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"access_manifest_rule_{key}_required:{index}")
    return value.strip()
