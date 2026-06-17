from __future__ import annotations

import json
from datetime import timedelta
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

from democrai.core.application.ai.engine.orchestrator.node_views import (
    NodeResourcesView,
    load_active_node_views,
)
from democrai.core.application.ai.orchestrator import ModelOrchestrator
from democrai.core.infrastructure.database.models import (
    Base,
    EngineNodeInstanceRegistry,
    EngineRegistry,
    ModelCapabilityPriority,
    ModelRegistry,
    RuntimeNodeRegistry,
)
from democrai.core.platform.utils.timezone import utc_now_naive


def _fake_model(*, engine_row_id: int = 9, model_id: int = 11) -> SimpleNamespace:
    return SimpleNamespace(
        id=model_id,
        engine=SimpleNamespace(provider="llamacpp", id=engine_row_id),
        available_model=None,
        extra_config={},
        is_downloaded=True,
        status="active",
    )


@pytest.fixture
def scoring_orchestrator(monkeypatch):
    orch = ModelOrchestrator(session_factory=lambda: None)
    monkeypatch.setattr(
        ModelOrchestrator, "_provider_capabilities", classmethod(lambda cls, m: {"chat"})
    )
    monkeypatch.setattr(
        ModelOrchestrator, "_catalog_model_metadata", classmethod(lambda cls, m: {})
    )
    monkeypatch.setattr(
        ModelOrchestrator,
        "memory_requirements_mb",
        classmethod(lambda cls, m: (32_000, 16_000)),
    )
    monkeypatch.setattr(
        ModelOrchestrator, "_effective_policy_mode", lambda self, p, **kw: "hybrid"
    )
    monkeypatch.setattr(
        ModelOrchestrator, "_engine_fit_score", lambda self, provider, caps: 0
    )
    monkeypatch.setattr(
        ModelOrchestrator, "_is_local_provider", staticmethod(lambda provider: True)
    )
    return orch


def _score(orch, model, **kwargs):
    return orch._score_model_candidate(
        model,
        objective="chat",
        required_capabilities=["chat"],
        policy={},
        mapped_model=None,
        prefer_local=None,
        **kwargs,
    )


def test_default_resources_equivalent_to_explicit_local(scoring_orchestrator):
    local = SimpleNamespace(ram_gb=64.0, vram_gb=24.0, has_gpu=True)
    scoring_orchestrator.hardware = SimpleNamespace(
        get_system_resources=lambda: local
    )
    model = _fake_model()
    assert _score(scoring_orchestrator, model) == _score(
        scoring_orchestrator, model, resources=local
    )


def test_view_with_insufficient_resources_scores_lower(scoring_orchestrator):
    model = _fake_model()
    rich = NodeResourcesView(node_id="a", has_gpu=True, ram_gb=64.0, vram_gb=24.0)
    starved = NodeResourcesView(node_id="b", has_gpu=True, ram_gb=8.0, vram_gb=2.0)
    no_gpu = NodeResourcesView(node_id="c", has_gpu=False, ram_gb=64.0, vram_gb=0.0)
    rich_score = _score(scoring_orchestrator, model, resources=rich)
    assert _score(scoring_orchestrator, model, resources=starved) < rich_score
    assert _score(scoring_orchestrator, model, resources=no_gpu) < rich_score


def test_warm_instance_bonus(scoring_orchestrator):
    model = _fake_model(engine_row_id=9, model_id=11)
    view = NodeResourcesView(node_id="a", has_gpu=True, ram_gb=64.0, vram_gb=24.0)
    warm_view = NodeResourcesView(
        node_id="a",
        has_gpu=True,
        ram_gb=64.0,
        vram_gb=24.0,
        warm_instances=frozenset({(9, 11)}),
    )
    cold = _score(
        scoring_orchestrator, model, resources=view, warm_instances=view.warm_instances
    )
    warm = _score(
        scoring_orchestrator,
        model,
        resources=warm_view,
        warm_instances=warm_view.warm_instances,
    )
    assert warm == cold + 50


def test_warm_bonus_requires_matching_pair(scoring_orchestrator):
    model = _fake_model(engine_row_id=9, model_id=11)
    view = NodeResourcesView(
        node_id="a",
        has_gpu=True,
        ram_gb=64.0,
        vram_gb=24.0,
        warm_instances=frozenset({(9, 99)}),
    )
    cold = _score(scoring_orchestrator, model, resources=view)
    assert (
        _score(
            scoring_orchestrator,
            model,
            resources=view,
            warm_instances=view.warm_instances,
        )
        == cold
    )


@pytest.fixture
def db_session_factory(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'views.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    yield factory
    engine.dispose()


def test_load_active_node_views_filters_stale_and_collects_warm(db_session_factory):
    now = utc_now_naive()
    with db_session_factory() as session:
        session.add(
            RuntimeNodeRegistry(
                node_id="node-fresh",
                has_nvidia_gpu=True,
                orchestrator_last_seen_at=now,
                ram_total_mb=65_536,
                ram_free_mb=32_768,
                vram_total_mb=24_576,
                vram_free_mb=12_288,
                cpu_percent=12.5,
            )
        )
        session.add(
            RuntimeNodeRegistry(
                node_id="node-stale",
                has_nvidia_gpu=True,
                orchestrator_last_seen_at=now - timedelta(seconds=120),
                ram_free_mb=65_536,
            )
        )
        session.add(
            RuntimeNodeRegistry(node_id="node-never", orchestrator_last_seen_at=None)
        )
        session.add(
            EngineNodeInstanceRegistry(
                node_id="node-fresh",
                engine_row_id=9,
                engine_id="llamacpp",
                model_registry_id=11,
                status="running",
            )
        )
        session.add(
            EngineNodeInstanceRegistry(
                node_id="node-fresh",
                engine_row_id=9,
                engine_id="llamacpp",
                model_registry_id=12,
                status="loading",
            )
        )
        session.add(
            EngineNodeInstanceRegistry(
                node_id="node-stale",
                engine_row_id=9,
                engine_id="llamacpp",
                model_registry_id=11,
                status="running",
            )
        )
        session.commit()

    views = load_active_node_views(
        threshold_seconds=10, session_factory=db_session_factory, now=now
    )
    assert [view.node_id for view in views] == ["node-fresh"]
    view = views[0]
    assert view.has_gpu is True
    assert view.ram_gb == 32.0
    assert view.vram_gb == 12.0
    assert view.cpu_percent == 12.5
    # loading instances are claims in flight, not warm handles
    assert view.warm_instances == frozenset({(9, 11)})


def test_score_selector_for_view_objective_and_model_id(
    db_session_factory, monkeypatch
):
    with db_session_factory() as session:
        engine_row = EngineRegistry(name="llamacpp", provider="llamacpp", status="active")
        session.add(engine_row)
        session.flush()
        model_row = ModelRegistry(
            name="qwen",
            engine_id=engine_row.id,
            status="active",
        )
        session.add(model_row)
        session.flush()
        model_id = model_row.id
        engine_id = engine_row.id
        session.commit()

    orch = ModelOrchestrator(session_factory=db_session_factory)
    monkeypatch.setattr(
        ModelOrchestrator, "_provider_capabilities", classmethod(lambda cls, m: {"chat"})
    )
    monkeypatch.setattr(
        ModelOrchestrator, "_catalog_model_metadata", classmethod(lambda cls, m: {})
    )
    monkeypatch.setattr(
        ModelOrchestrator,
        "memory_requirements_mb",
        classmethod(lambda cls, m: (16_000, 8_000)),
    )
    monkeypatch.setattr(
        ModelOrchestrator, "_effective_policy_mode", lambda self, p, **kw: "hybrid"
    )
    monkeypatch.setattr(
        ModelOrchestrator, "_engine_fit_score", lambda self, provider, caps: 0
    )
    monkeypatch.setattr(
        ModelOrchestrator, "_is_local_provider", staticmethod(lambda provider: True)
    )
    monkeypatch.setattr(
        ModelOrchestrator, "_load_selection_policy", lambda self: {}
    )

    warm_view = NodeResourcesView(
        node_id="a",
        has_gpu=True,
        ram_gb=64.0,
        vram_gb=24.0,
        warm_instances=frozenset({(engine_id, model_id)}),
    )
    cold_view = NodeResourcesView(node_id="b", has_gpu=True, ram_gb=64.0, vram_gb=24.0)

    warm = orch.score_selector_for_view(
        selector_type="objective", objective="chat", view=warm_view
    )
    cold = orch.score_selector_for_view(
        selector_type="objective", objective="chat", view=cold_view
    )
    assert warm is not None and cold is not None
    assert warm == cold + 50

    by_id_cold = orch.score_selector_for_view(
        selector_type="model_registry_id",
        model_registry_id=model_id,
        view=cold_view,
    )
    by_id_warm = orch.score_selector_for_view(
        selector_type="model_registry_id",
        model_registry_id=model_id,
        view=warm_view,
    )
    assert by_id_cold is not None and by_id_warm == by_id_cold + 50

    assert (
        orch.score_selector_for_view(
            selector_type="model_registry_id",
            model_registry_id=999,
            view=cold_view,
        )
        is None
    )

    with pytest.raises(RuntimeError, match="selector_unknown"):
        orch.score_selector_for_view(selector_type="bogus", view=cold_view)


def _seed_priority_models(
    db_session_factory,
    *,
    include_unprioritized: bool = False,
    include_priorities: bool = True,
):
    with db_session_factory() as session:
        first_engine = EngineRegistry(
            name="engine-first",
            provider="engine-first",
            status="active",
        )
        second_engine = EngineRegistry(
            name="engine-second",
            provider="engine-second",
            status="active",
        )
        session.add_all([first_engine, second_engine])
        session.flush()
        first_model = ModelRegistry(
            name="model-first",
            engine_id=first_engine.id,
            status="active",
        )
        second_model = ModelRegistry(
            name="model-second",
            engine_id=second_engine.id,
            status="active",
        )
        session.add_all([first_model, second_model])
        session.flush()
        if include_priorities:
            session.add_all(
                [
                    ModelCapabilityPriority(
                        capability="chat",
                        model_id=first_model.id,
                        priority=1,
                    ),
                    ModelCapabilityPriority(
                        capability="chat",
                        model_id=second_model.id,
                        priority=2,
                    ),
                ]
            )
        unprioritized_model_id = None
        if include_unprioritized:
            third_engine = EngineRegistry(
                name="engine-third",
                provider="engine-third",
                status="active",
            )
            session.add(third_engine)
            session.flush()
            third_model = ModelRegistry(
                name="model-third",
                engine_id=third_engine.id,
                status="active",
            )
            session.add(third_model)
            session.flush()
            unprioritized_model_id = third_model.id
        payload = {
            "first_engine_id": first_engine.id,
            "second_engine_id": second_engine.id,
            "first_model_id": first_model.id,
            "second_model_id": second_model.id,
            "unprioritized_model_id": unprioritized_model_id,
        }
        session.commit()
        return payload


def _patch_objective_selection(monkeypatch):
    monkeypatch.setattr(
        ModelOrchestrator, "_provider_capabilities", classmethod(lambda cls, m: {"chat"})
    )
    monkeypatch.setattr(
        ModelOrchestrator, "_catalog_model_metadata", classmethod(lambda cls, m: {})
    )
    monkeypatch.setattr(
        ModelOrchestrator, "_load_selection_policy", lambda self: {}
    )
    monkeypatch.setattr(
        ModelOrchestrator,
        "_effective_policy_mode",
        lambda self, p, **kw: "hybrid",
    )
    monkeypatch.setattr(
        ModelOrchestrator, "_engine_fit_score", lambda self, provider, caps: 0
    )
    monkeypatch.setattr(
        ModelOrchestrator, "_is_local_provider", staticmethod(lambda provider: True)
    )


def test_quota_aware_objective_selection_skips_exhausted_priority_model(
    db_session_factory, monkeypatch
):
    ids = _seed_priority_models(db_session_factory)
    _patch_objective_selection(monkeypatch)

    calls = []

    def fake_check_engine_quota(**kwargs):
        calls.append(kwargs["engine_registry_id"])
        if kwargs["engine_registry_id"] == ids["first_engine_id"]:
            return SimpleNamespace(allowed=False, reason="engine_quota_exceeded")
        return SimpleNamespace(allowed=True, reason="engine_quota_available")

    import democrai.core.application.ai.engine.quotas as quotas_mod

    monkeypatch.setattr(quotas_mod, "check_engine_quota", fake_check_engine_quota)

    orch = ModelOrchestrator(session_factory=db_session_factory)
    model, quota_exhausted = orch.get_quota_available_model_for_objective(
        "chat",
        request_context={"user": 7},
    )

    assert quota_exhausted is False
    assert model is not None
    assert model.id == ids["second_model_id"]
    assert calls == [ids["first_engine_id"], ids["second_engine_id"]]


def test_quota_aware_objective_selection_ignores_unprioritized_fallbacks(
    db_session_factory, monkeypatch
):
    ids = _seed_priority_models(db_session_factory, include_unprioritized=True)
    _patch_objective_selection(monkeypatch)

    def fake_check_engine_quota(**_kwargs):
        return SimpleNamespace(allowed=False, reason="engine_quota_exceeded")

    import democrai.core.application.ai.engine.quotas as quotas_mod

    monkeypatch.setattr(quotas_mod, "check_engine_quota", fake_check_engine_quota)

    orch = ModelOrchestrator(session_factory=db_session_factory)
    model, quota_exhausted = orch.get_quota_available_model_for_objective(
        "chat",
        request_context={"user": 7},
    )

    assert model is None
    assert quota_exhausted is True
    assert ids["unprioritized_model_id"] is not None


def test_get_model_for_objective_keeps_first_priority_without_quota_context(
    db_session_factory, monkeypatch
):
    ids = _seed_priority_models(db_session_factory)
    _patch_objective_selection(monkeypatch)

    import democrai.core.application.ai.engine.quotas as quotas_mod

    monkeypatch.setattr(
        quotas_mod,
        "check_engine_quota",
        lambda **_kwargs: pytest.fail("quota should not be checked"),
    )

    orch = ModelOrchestrator(session_factory=db_session_factory)
    model = orch.get_model_for_objective("chat")

    assert model is not None
    assert model.id == ids["first_model_id"]


def test_quota_fallback_is_not_applied_without_capability_priorities(
    db_session_factory, monkeypatch
):
    ids = _seed_priority_models(db_session_factory, include_priorities=False)
    _patch_objective_selection(monkeypatch)

    import democrai.core.application.ai.engine.quotas as quotas_mod

    monkeypatch.setattr(
        quotas_mod,
        "check_engine_quota",
        lambda **_kwargs: pytest.fail("quota should not be checked"),
    )

    orch = ModelOrchestrator(session_factory=db_session_factory)
    model, quota_exhausted = orch.get_quota_available_model_for_objective(
        "chat",
        request_context={"user": 7},
    )

    assert quota_exhausted is False
    assert model is not None
    assert model.id == ids["first_model_id"]


def test_validate_selector_uses_quota_aware_capability_fallback(
    db_session_factory, monkeypatch
):
    ids = _seed_priority_models(db_session_factory)
    _patch_objective_selection(monkeypatch)

    def fake_check_engine_quota(**kwargs):
        if kwargs["engine_registry_id"] == ids["first_engine_id"]:
            return SimpleNamespace(allowed=False, reason="engine_quota_exceeded")
        return SimpleNamespace(allowed=True, reason="engine_quota_available")

    import democrai.core.application.ai.engine.quotas as quotas_mod
    import democrai.core.application.ai.engine.orchestrator.resolver as resolver_mod
    import democrai.core.application.ai.orchestrator as orchestrator_mod

    monkeypatch.setattr(quotas_mod, "check_engine_quota", fake_check_engine_quota)
    monkeypatch.setattr(
        orchestrator_mod,
        "model_orchestrator",
        ModelOrchestrator(session_factory=db_session_factory),
    )

    request = SimpleNamespace(
        selector_type="capability",
        model_registry_id=0,
        objective="",
        capability="chat",
        capabilities_json=json.dumps([]),
        prefer_local=None,
        request_context_json=json.dumps({"user": 7}),
    )

    result = resolver_mod.validate_selector(request)

    assert result["status"] == "ok"
    assert result["model_registry_id"] == ids["second_model_id"]
    assert result["engine"] == "engine-second"


def test_validate_selector_model_registry_id_does_not_use_quota_fallback(
    db_session_factory, monkeypatch
):
    ids = _seed_priority_models(db_session_factory)

    import democrai.core.application.ai.engine.quotas as quotas_mod
    import democrai.core.application.ai.engine.orchestrator.resolver as resolver_mod
    import democrai.core.application.ai.orchestrator as orchestrator_mod

    monkeypatch.setattr(
        quotas_mod,
        "check_engine_quota",
        lambda **_kwargs: pytest.fail("quota should not be checked"),
    )
    monkeypatch.setattr(
        orchestrator_mod,
        "model_orchestrator",
        ModelOrchestrator(session_factory=db_session_factory),
    )

    request = SimpleNamespace(
        selector_type="model_registry_id",
        model_registry_id=ids["first_model_id"],
        objective="",
        capability="",
        capabilities_json=json.dumps([]),
        prefer_local=None,
        request_context_json=json.dumps({"user": 7}),
    )

    result = resolver_mod.validate_selector(request)

    assert result["status"] == "ok"
    assert result["model_registry_id"] == ids["first_model_id"]
