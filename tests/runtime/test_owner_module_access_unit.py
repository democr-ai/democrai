from __future__ import annotations

from types import SimpleNamespace

import pytest

import democrai.core.application.ai.pipeline_context as pipeline_context_mod
import democrai.core.infrastructure.sandbox.process_guard as guard_mod
from democrai.core.application.access_policy import AccessManifestRule
from democrai.core.application.access_policy import AccessResource
from democrai.core.application.access_policy import AccessSubject
from democrai.core.infrastructure.sandbox.owner_module_access import OwnerModuleAccess
from democrai.core.infrastructure.sandbox.worker_launch import (
    build_worker_launch_state,
)
from democrai.core.runtime.foundation.app import app_ctx


def _module_rule(module: str, target: str) -> AccessManifestRule:
    return AccessManifestRule(
        subject=AccessSubject.create("module", module),
        resource=AccessResource.create(
            resource_type="filesystem",
            operation="read",
            target=target,
        ),
    )


def _state_with_chain(chain: list[dict]) -> dict:
    return {"subject_access_chain": chain}


def test_resolves_innermost_module_frame_with_chain_access(monkeypatch):
    monkeypatch.setattr(app_ctx(), "modules", None, raising=False)
    chain = [
        {"kind": "module", "name": "outer", "access": [_module_rule("outer", "/outer").to_dict()]},
        {"kind": "module", "name": "demo", "access": [_module_rule("demo", "/demo/data").to_dict()]},
        {"kind": "skill", "name": "demo.skill", "access": []},
    ]
    token = guard_mod._STATE.set(_state_with_chain(chain))
    try:
        name, access = OwnerModuleAccess.resolve()
    finally:
        guard_mod._STATE.reset(token)

    assert name == "demo"
    assert [rule.resource.target for rule in access] == ["/demo/data"]


def test_registry_access_preferred_over_chain_snapshot(monkeypatch):
    registry_rule = _module_rule("demo", "/registry/path")

    class _Modules:
        def get_module(self, name):
            assert name == "demo"
            return SimpleNamespace(access=(registry_rule,))

    monkeypatch.setattr(app_ctx(), "modules", _Modules(), raising=False)
    chain = [
        {"kind": "module", "name": "demo", "access": [_module_rule("demo", "/stale/path").to_dict()]},
    ]
    token = guard_mod._STATE.set(_state_with_chain(chain))
    try:
        name, access = OwnerModuleAccess.resolve()
    finally:
        guard_mod._STATE.reset(token)

    assert name == "demo"
    assert [rule.resource.target for rule in access] == ["/registry/path"]


def test_falls_back_to_pipeline_caller_module(monkeypatch):
    registry_rule = _module_rule("chatmod", "/chatmod/files")

    class _Modules:
        def get_module(self, name):
            assert name == "chatmod"
            return SimpleNamespace(access=(registry_rule,))

    monkeypatch.setattr(app_ctx(), "modules", _Modules(), raising=False)
    monkeypatch.setattr(
        pipeline_context_mod,
        "current_ai_pipeline_context",
        lambda: SimpleNamespace(caller_module="ChatMod"),
    )
    token = guard_mod._STATE.set(_state_with_chain([]))
    try:
        name, access = OwnerModuleAccess.resolve()
        assert OwnerModuleAccess.resolve_name() == "chatmod"
    finally:
        guard_mod._STATE.reset(token)

    assert name == "chatmod"
    assert [rule.resource.target for rule in access] == ["/chatmod/files"]


def test_unresolved_owner_module_fails_loudly(monkeypatch):
    monkeypatch.setattr(app_ctx(), "modules", None, raising=False)
    monkeypatch.setattr(
        pipeline_context_mod,
        "current_ai_pipeline_context",
        lambda: None,
    )
    token = guard_mod._STATE.set(
        _state_with_chain([{"kind": "skill", "name": "orphan", "access": []}])
    )
    try:
        with pytest.raises(RuntimeError, match="owner_module_unresolved"):
            OwnerModuleAccess.resolve()
        with pytest.raises(RuntimeError, match="owner_module_unresolved"):
            OwnerModuleAccess.resolve_name()
    finally:
        guard_mod._STATE.reset(token)


def test_resolved_name_without_any_access_source_fails_loudly(monkeypatch):
    monkeypatch.setattr(app_ctx(), "modules", None, raising=False)
    # Chain frame names the module but carries no serialized access and the
    # registry is unavailable: surfacing an empty grant would be a silent
    # security downgrade, so it must raise instead.
    token = guard_mod._STATE.set(
        _state_with_chain([{"kind": "module", "name": "demo"}])
    )
    try:
        with pytest.raises(RuntimeError, match="owner_module_access_unresolved:demo"):
            OwnerModuleAccess.resolve()
    finally:
        guard_mod._STATE.reset(token)


def test_engine_worker_launch_state_gets_no_module_access():
    # Explicit non-goal: engines do not inherit module access. Module file
    # reads are mediated by the orchestrator (parent media requests).
    module_only_target = "/module/private/data"
    state = {
        "subject": "demo",
        "subject_kind": "module",
        "subject_chain": ({"kind": "module", "name": "demo"},),
        "access": (_module_rule("demo", module_only_target),),
        "subject_access_chain": [
            {
                "kind": "module",
                "name": "demo",
                "access": [_module_rule("demo", module_only_target).to_dict()],
            }
        ],
    }
    token = guard_mod._STATE.set(state)
    try:
        launch_state = build_worker_launch_state(
            subject_kind="engine",
            subject_name="llamacpp",
            access=(),
        )
    finally:
        guard_mod._STATE.reset(token)

    targets = {rule.resource.target for rule in launch_state["access"]}
    assert module_only_target not in targets
