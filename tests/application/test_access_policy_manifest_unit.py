from __future__ import annotations

import json
from pathlib import Path

import pytest

from democrai.core.application.access_policy import AccessOperation
from democrai.core.application.access_policy import ResourceType
from democrai.core.application.access_policy import parse_access_manifest_rules
from democrai.core.application.access_policy.keys import access_fingerprint
import democrai.core.application.access_policy.manifest as manifest_mod


def test_parse_access_manifest_rules_accepts_canonical_access_list():
    rules = parse_access_manifest_rules(
        {
            "access": [
                {
                    "resource_type": "network",
                    "operation": "receive",
                    "target": "HTTPS://huggingface.co/models",
                },
                {
                    "resource_type": "filesystem",
                    "operation": "read",
                    "target": "/tmp/models",
                },
            ],
        },
        subject_type="engine",
        subject_name="whisper",
    )

    assert len(rules) == 2
    assert rules[0].subject.subject_type == "engine"
    assert rules[0].subject.subject_name == "whisper"
    assert rules[0].resource.resource_type == ResourceType.NETWORK
    assert rules[0].resource.operation == AccessOperation.RECEIVE
    assert rules[0].resource.normalized_target == "https://huggingface.co/models"
    assert rules[1].resource.resource_type == ResourceType.FILESYSTEM
    assert rules[1].resource.operation == AccessOperation.READ


def test_parse_access_manifest_rules_missing_access_means_no_rules():
    assert (
        parse_access_manifest_rules(
            {},
            subject_type="module",
            subject_name="system",
        )
        == ()
    )


def test_parse_access_manifest_rules_resolves_data_dir_token(monkeypatch, tmp_path):
    data_root = tmp_path / "Library" / "Application Support" / "democrai"
    data_root.mkdir(parents=True)
    monkeypatch.setattr(manifest_mod, "data_dir", lambda: data_root)

    rules = parse_access_manifest_rules(
        {
            "access": [
                {
                    "resource_type": "filesystem",
                    "operation": "create",
                    "target": "{data_dir}",
                },
            ],
        },
        subject_type="module",
        subject_name="system",
    )

    assert len(rules) == 1
    assert rules[0].resource.target == str(data_root.resolve())
    assert rules[0].resource.normalized_target == str(data_root.resolve())


def test_parse_access_manifest_rules_rejects_unresolved_filesystem_token():
    with pytest.raises(ValueError, match="access_manifest_unresolved_filesystem_token"):
        parse_access_manifest_rules(
            {
                "access": [
                    {
                        "resource_type": "filesystem",
                        "operation": "read",
                        "target": "{unknown}",
                    },
                ],
            },
            subject_type="module",
            subject_name="demo",
        )


def test_parse_access_manifest_rules_keeps_network_token_text():
    rules = parse_access_manifest_rules(
        {
            "access": [
                {
                    "resource_type": "network",
                    "operation": "receive",
                    "target": "https://{tenant}.example.test/*",
                },
            ],
        },
        subject_type="module",
        subject_name="demo",
    )

    assert rules[0].resource.target == "https://{tenant}.example.test/*"


def test_parse_access_manifest_rules_rejects_non_canonical_shapes():
    with pytest.raises(TypeError, match="access_manifest_access_must_be_list"):
        parse_access_manifest_rules(
            {"access": {"network": {"receive": ["https://x"]}}},
            subject_type="module",
            subject_name="system",
        )

    with pytest.raises(TypeError, match="access_manifest_rule_must_be_dict:0"):
        parse_access_manifest_rules(
            {"access": ["https://x"]},
            subject_type="module",
            subject_name="system",
        )


def test_parse_access_manifest_rules_rejects_missing_fields():
    with pytest.raises(ValueError, match="access_manifest_rule_resource_type_required:0"):
        parse_access_manifest_rules(
            {"access": [{"operation": "receive", "target": "https://x"}]},
            subject_type="module",
            subject_name="system",
        )
    with pytest.raises(ValueError, match="access_manifest_rule_operation_required:0"):
        parse_access_manifest_rules(
            {"access": [{"resource_type": "network", "target": "https://x"}]},
            subject_type="module",
            subject_name="system",
        )
    with pytest.raises(ValueError, match="access_manifest_rule_target_required:0"):
        parse_access_manifest_rules(
            {"access": [{"resource_type": "network", "operation": "receive"}]},
            subject_type="module",
            subject_name="system",
        )


def test_parse_access_manifest_rules_rejects_invalid_operation_for_resource():
    with pytest.raises(ValueError, match="invalid_access_operation_for_resource"):
        parse_access_manifest_rules(
            {
                "access": [
                    {
                        "resource_type": "network",
                        "operation": "delete",
                        "target": "https://x",
                    }
                ]
            },
            subject_type="module",
            subject_name="system",
        )


def test_parse_access_manifest_rules_same_target_different_operation_are_distinct():
    rules = parse_access_manifest_rules(
        {
            "access": [
                {
                    "resource_type": "network",
                    "operation": "receive",
                    "target": "https://api.example.com",
                },
                {
                    "resource_type": "network",
                    "operation": "send",
                    "target": "https://api.example.com",
                },
            ],
        },
        subject_type="agent",
        subject_name="assistant",
    )

    assert len(rules) == 2
    fingerprints = {
        access_fingerprint(subject=rule.subject, resource=rule.resource)
        for rule in rules
    }
    assert len(fingerprints) == 2


def test_parse_access_manifest_rules_filters_by_resource_and_operation_without_helper():
    manifest = {
        "access": [
            {
                "resource_type": "network",
                "operation": "receive",
                "target": "https://api.example.com",
            },
            {
                "resource_type": "network",
                "operation": "send",
                "target": "https://api.example.com",
            },
            {
                "resource_type": "filesystem",
                "operation": "read",
                "target": "/tmp/models",
            },
        ],
    }

    rules = parse_access_manifest_rules(
        manifest,
        subject_type="module",
        subject_name="system",
    )

    assert [
        rule.resource.target
        for rule in rules
        if rule.resource.resource_type == ResourceType.NETWORK
        and rule.resource.operation == AccessOperation.RECEIVE
    ] == ["https://api.example.com"]
    assert [
        rule.resource.target
        for rule in rules
        if rule.resource.resource_type == ResourceType.FILESYSTEM
        and rule.resource.operation in {AccessOperation.READ, AccessOperation.MODIFY}
    ] == ["/tmp/models"]


def test_module_and_extractor_manifests_do_not_use_ungated_absolute_filesystem_paths():
    violations: list[str] = []
    for base in ("modules", "extractors"):
        for path in Path(base).glob("*/manifest.json"):
            manifest = json.loads(path.read_text(encoding="utf-8"))
            sections = [("root", manifest)]
            sections.extend(
                (key, value)
                for key, value in manifest.items()
                if isinstance(value, dict)
            )
            for section_name, section in sections:
                for item in section.get("access") or ():
                    target = str(item.get("target") or "")
                    if target.startswith("/"):
                        violations.append(f"{path}:{section_name}:{target}")

    assert violations == []
