from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from democrai.core.application.auth.roles import (
    ROLE_LEVEL_ORGANIZATION,
    ROLE_LEVEL_SUPER,
    ROLE_LEVEL_USER,
)
from democrai.core.application.models.context import CoreModelContext
from democrai.core.platform.utils.normalize import normalize_bool
import democrai.core.application.models.entities._observability as obs_mod
import democrai.core.application.ai.engine.config_crypto as eng_crypto_mod
import democrai.core.application.models.entities.audit_events as audit_mod
import democrai.core.application.models.entities.background_tasks as bg_mod
import democrai.core.application.models.entities.engine_node_install_registry as enir_mod
import democrai.core.application.models.entities.engine_quota_counters as eqc_mod
import democrai.core.application.models.entities.engine_quota_limits as eql_mod
import democrai.core.application.models.entities.engine_registry as er_mod
import democrai.core.application.models.entities.extractor_node_install_registry as exnir_mod
import democrai.core.application.models.entities.extractor_registry as exr_mod
import democrai.core.application.models.entities.ai_model_pipeline_steps as ai_steps_mod
import democrai.core.application.models.entities.ai_model_usage as ai_usage_mod
import democrai.core.application.models.entities.model_capability_priority as mcp_mod
import democrai.core.application.models.entities.model_registry as mr_mod
import democrai.core.application.models.entities.module_locks as ml_mod
import democrai.core.application.models.entities.objective_mappings as om_mod
import democrai.core.application.models.entities.roles as roles_mod
import democrai.core.application.models.entities.users as users_mod
from democrai.core.application.ai.constants import normalize_capability
from democrai.core.infrastructure.database.models import (
    Base,
    EngineRegistry,
    ExtractorRegistry,
    ModelRegistry,
    ModuleLock,
    Permission,
    Role,
    User,
)
from democrai.core.infrastructure.database.models_engine_quota import (
    EngineQuotaCounter,
    EngineQuotaLimit,
)
from democrai.core.infrastructure.storage.observability.models import (
    AuditEvent,
    Base as ObsBase,
    AIModelPipelineStep,
    AIModelUsageEvent,
)


class _CollectingQuery:
    def __init__(self):
        self.filters = []

    def filter(self, *args):
        self.filters.extend(args)
        return self


@pytest.fixture()
def core_session_local(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )

    for mod in (
        er_mod,
        eqc_mod,
        eql_mod,
        exr_mod,
        mcp_mod,
        mr_mod,
        ml_mod,
        om_mod,
        roles_mod,
        users_mod,
    ):
        monkeypatch.setattr(mod, "SessionLocal", SessionLocal)

    yield SessionLocal

    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def obs_session_local(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    ObsBase.metadata.create_all(engine)
    SessionLocal = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )

    provider = SimpleNamespace(SessionLocal=SessionLocal)
    monkeypatch.setattr(obs_mod, "app_ctx", lambda: SimpleNamespace(obs_store=SimpleNamespace(provider=provider)))

    yield SessionLocal

    ObsBase.metadata.drop_all(engine)
    engine.dispose()


def _ctx(access_level: int = ROLE_LEVEL_SUPER, user_id: int = 1, organization_id: int | None = 10, bypass: bool = False) -> CoreModelContext:
    return CoreModelContext(
        user_id=user_id,
        organization_id=organization_id,
        access_level=access_level,
        module_name="system",
        session={},
        bypass=bypass,
    )


def _seed_engine(session, *, name: str = "eng1") -> EngineRegistry:
    row = EngineRegistry(name=name, provider="prov", config={"a": 1}, status="installed", supported=True)
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def _seed_model(session, engine_id: int, *, name: str = "model1") -> ModelRegistry:
    row = ModelRegistry(name=name, engine_id=engine_id, status="available", is_downloaded=0)
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def test_observability_core_model_session_factory_and_read_only(obs_session_local, monkeypatch):
    class _ConcreteObs(obs_mod.ObservabilityCoreModel):
        name = "obs_dummy"

        def serialize_row(self, item):
            return {"id": getattr(item, "id", None)}

    model = _ConcreteObs(_ctx())

    sf = model._session_factory()
    assert callable(sf)
    assert sf is obs_session_local

    monkeypatch.setattr(obs_mod, "app_ctx", lambda: SimpleNamespace(obs_store=SimpleNamespace(provider=SimpleNamespace(SessionLocal=None))))
    with pytest.raises(RuntimeError, match="observability core models require a SQLAlchemy observability provider"):
        model._session_factory()

    with pytest.raises(NotImplementedError, match="is read-only"):
        model.create({})
    with pytest.raises(NotImplementedError, match="is read-only"):
        model.update(1, {})
    with pytest.raises(NotImplementedError, match="is read-only"):
        model.delete(1)


def test_engine_quota_core_models_create_update_delete_and_registry(core_session_local):
    from democrai.core.application.models import build_core_model
    from democrai.core.application.models import list_core_models

    with core_session_local() as session:
        engine = _seed_engine(session)

    assert "engine_quota_counters" in list_core_models()
    assert "engine_quota_limits" in list_core_models()

    counters = build_core_model("engine_quota_counters", _ctx())
    limits = build_core_model("engine_quota_limits", _ctx())

    counter = counters.create({"name": "daily tokens", "period_unit": "day"})
    assert counter["period_unit"] == "day"
    updated_counter = counters.update(counter["id"], {"period_unit": "hour"})
    assert updated_counter["period_unit"] == "hour"

    limit = limits.create(
        {
            "counter_id": counter["id"],
            "engine_row_id": engine.id,
            "scope_type": "user",
            "scope_id": 1,
            "limit_total_tokens": 100,
        }
    )
    assert limit["limit_total_tokens"] == 100
    updated_limit = limits.update(limit["id"], {"limit_total_tokens": 50})
    assert updated_limit["limit_total_tokens"] == 50

    with pytest.raises(ValueError, match="period_unit unsupported"):
        counters.create({"name": "bad", "period_unit": "year"})
    with pytest.raises(ValueError, match="scope_id is required"):
        limits.create(
            {
                "counter_id": counter["id"],
                "engine_row_id": engine.id,
                "scope_type": "role",
                "limit_total_tokens": 10,
            }
        )
    with pytest.raises(ValueError, match="limit_total_tokens must be >= 0"):
        limits.create(
            {
                "counter_id": counter["id"],
                "engine_row_id": engine.id,
                "scope_type": "all",
                "limit_total_tokens": -1,
            }
        )

    assert limits.delete(limit["id"]) is True
    assert counters.delete(counter["id"]) is True


def test_audit_events_model_serialization_and_filters(obs_session_local):
    model = audit_mod.AuditEventsCoreModel(_ctx())
    with obs_session_local() as session:
        row = AuditEvent(
            event_type="auth.login",
            actor_user_id=7,
            actor_role="user",
            organization_id=22,
            session_id="s1",
            request_id="r1",
            correlation_id="c1",
            client_ip="127.0.0.1",
            channel="ws",
            entity_type="user",
            entity_id="7",
            operation="login",
            status="ok",
        )
        session.add(row)
        session.commit()
        session.refresh(row)

        serialized = model.serialize_row(row)
        assert serialized["event_type"] == "auth.login"
        assert serialized["actor_user_id"] == 7
        assert model.serialize_detail(row)["actor_role"] == "user"

    assert model._default_sort() == ("timestamp", "desc")
    assert len(model.filters_model()) == 6
    assert len(model.table_model()) == 7

    q = _CollectingQuery()
    model._apply_filters(q, {
        "event_type": "auth",
        "entity_type": "user",
        "entity_id": "7",
        "operation": "log",
        "status": "ok",
        "actor_user_id": "12",
    })
    assert len(q.filters) == 6

    q_bad = _CollectingQuery()
    model._apply_filters(q_bad, {"actor_user_id": "bad"})
    assert q_bad.filters == []


def test_audit_events_access_scope_branches():
    q = _CollectingQuery()
    assert audit_mod.AuditEventsCoreModel(_ctx(bypass=True))._apply_access_scope(q) is q
    assert audit_mod.AuditEventsCoreModel(_ctx(access_level=ROLE_LEVEL_SUPER))._apply_access_scope(q) is q

    q_org = _CollectingQuery()
    audit_mod.AuditEventsCoreModel(_ctx(access_level=ROLE_LEVEL_ORGANIZATION, organization_id=33))._apply_access_scope(q_org)
    assert len(q_org.filters) == 1

    q_user = _CollectingQuery()
    audit_mod.AuditEventsCoreModel(_ctx(access_level=ROLE_LEVEL_USER, user_id=99))._apply_access_scope(q_user)
    assert len(q_user.filters) == 1


def test_background_tasks_model_paths():
    model = bg_mod.BackgroundTasksCoreModel(_ctx())
    item = bg_mod.BackgroundTaskRecord(
        id="t1",
        module="m",
        label="lbl",
        status="running",
        progress=0.5,
        task_key="k",
        user_id=9,
        organization_id=3,
        created_at=datetime(2026, 1, 1, 10, 0, 0),
        updated_at=datetime(2026, 1, 1, 10, 5, 0),
        checkpoint="cp",
        result="ok",
        error="",
    )
    assert model._default_sort() == ("updated_at", "desc")
    assert model.serialize_row(item)["id"] == "t1"
    assert model.serialize_detail(item)["checkpoint"] == "cp"
    assert len(model.filters_model()) == 7
    assert len(model.table_model()) == 6

    q = _CollectingQuery()
    model._apply_filters(
        q,
        {
            "id": "t1",
            "module": "m",
            "label": "l",
            "status": "run",
            "task_key": "k",
            "user_id": "8",
            "organization_id": "2",
        },
    )
    assert len(q.filters) == 7

    q_bad = _CollectingQuery()
    model._apply_filters(q_bad, {"user_id": "bad", "organization_id": object()})
    assert q_bad.filters == []

    with pytest.raises(NotImplementedError, match="read-only"):
        model.create({})
    with pytest.raises(NotImplementedError, match="read-only"):
        model.update(1, {})
    with pytest.raises(NotImplementedError, match="read-only"):
        model.delete(1)


def test_engine_and_extractor_node_install_registry_models():
    en_model = enir_mod.EngineNodeInstallRegistryCoreModel(_ctx())
    ex_model = exnir_mod.ExtractorNodeInstallRegistryCoreModel(_ctx())

    en_item = enir_mod.EngineNodeInstallRegistry(
        id=1,
        engine_id="eng",
        node_id="n1",
        status="installed",
        last_event_id="e1",
        last_error="",
        manifest_version="v1",
    )
    ex_item = exnir_mod.ExtractorNodeInstallRegistry(
        id=2,
        extractor_id="ext",
        node_id="n2",
        status="installing",
        last_event_id="e2",
        last_error="err",
        manifest_version="v2",
    )

    assert en_model._default_sort() == ("updated_at", "desc")
    assert ex_model._default_sort() == ("updated_at", "desc")
    assert en_model.serialize_row(en_item)["engine_id"] == "eng"
    assert ex_model.serialize_row(ex_item)["extractor_id"] == "ext"
    assert len(en_model.filters_model()) == 5
    assert len(ex_model.filters_model()) == 5
    assert len(en_model.table_model()) == 5
    assert len(ex_model.table_model()) == 5

    q1 = _CollectingQuery()
    en_model._apply_filters(q1, {"engine_id": " eng ", "node_id": "n", "status": "i", "last_event_id": "e", "id": "1"})
    assert len(q1.filters) == 5
    q2 = _CollectingQuery()
    ex_model._apply_filters(q2, {"extractor_id": " ext ", "node_id": "n", "status": "i", "last_event_id": "e", "id": "2"})
    assert len(q2.filters) == 5

    q1_bad = _CollectingQuery()
    en_model._apply_filters(q1_bad, {"engine_id": "   ", "id": "bad"})
    assert q1_bad.filters == []
    q2_bad = _CollectingQuery()
    ex_model._apply_filters(q2_bad, {"extractor_id": "   ", "id": object()})
    assert q2_bad.filters == []

    for m in (en_model, ex_model):
        with pytest.raises(NotImplementedError, match="read-only"):
            m.create({})
        with pytest.raises(NotImplementedError, match="read-only"):
            m.update(1, {})
        with pytest.raises(NotImplementedError, match="read-only"):
            m.delete(1)


@pytest.mark.parametrize(
    "value,default,expected",
    [
        (None, False, False),
        (None, True, True),
        (True, False, True),
        (False, True, False),
        (1, False, True),
        (0, True, False),
        ("yes", False, True),
        ("off", True, False),
        ("junk", True, True),
        ("junk", False, False),
    ],
)
def test_to_bool_helpers(value, default, expected):
    assert normalize_bool(value, default=default) is expected


def test_engine_registry_model_full_crud_and_filters(core_session_local, monkeypatch):
    monkeypatch.setattr(er_mod, "_request_os_allowlist_refresh", lambda **_kwargs: None)
    monkeypatch.setattr(
        eng_crypto_mod,
        "app_ctx",
        lambda: SimpleNamespace(
            config=SimpleNamespace(
                get=lambda key, default=None: (
                    "engine-secret-key"
                    if key == "app.engine_config_encryption_key"
                    else default
                )
            )
        ),
    )
    monkeypatch.setattr(
        eng_crypto_mod,
        "encrypted_keys_for_provider",
        lambda provider: ["api_key"] if str(provider or "").strip().lower() == "openai" else [],
    )
    monkeypatch.setattr(
        er_mod,
        "encrypted_keys_for_provider",
        lambda provider: ["api_key"] if str(provider or "").strip().lower() == "openai" else [],
    )
    model = er_mod.EngineRegistryCoreModel(_ctx())

    created = model.create(
        {
            "name": "engine-a",
            "provider": "openai",
            "config": {"k": 1, "api_key": "top-secret"},
            "status": "installed",
            "supported": "yes",
        }
    )
    assert created["name"] == "engine-a"
    assert created["supported"] is True
    assert created["config"]["api_key"] == "top-secret"

    with core_session_local() as s:
        stored = s.query(EngineRegistry).filter(EngineRegistry.id == int(created["id"])).first()
        assert isinstance(stored.config, dict)
        assert str(stored.config.get("api_key") or "").startswith("enc:v1:")

    invalid_row = model.serialize_row(
        EngineRegistry(
            id=9,
            name=None,
            provider=None,
            config=None,
            status=None,
            supported=0,
        )
    )
    assert invalid_row["status"] is None
    assert len(model.filters_model()) == 5
    assert len(model.table_model()) == 5

    q = _CollectingQuery()
    model._apply_filters(q, {"name": "eng", "provider": "op", "status": "inst", "id": "1", "supported": "true"})
    assert len(q.filters) == 5

    with pytest.raises(ValueError, match="name and provider are required"):
        model.create({"name": "", "provider": ""})
    with pytest.raises(ValueError, match="config must be an object"):
        model.create({"name": "x", "provider": "p", "config": []})
    with pytest.raises(ValueError, match="engine name already in use"):
        model.create({"name": "engine-a", "provider": "other"})

    assert model.update(999, {"name": "x"}) is None

    updated = model.update(
        created["id"],
        {"name": "engine-b", "provider": "openai", "config": {"k": 2}, "status": "", "supported": 0},
    )
    assert updated["name"] == "engine-b"
    assert updated["status"] == "uninstalled"
    assert updated["supported"] is False
    assert updated["config"]["api_key"] == "top-secret"

    cleared = model.update(updated["id"], {"config": {"api_key": ""}})
    assert isinstance(cleared, dict)
    assert cleared["config"]["api_key"] == ""

    model.create({"name": "engine-c", "provider": "prov"})
    with pytest.raises(ValueError, match="name is required"):
        model.update(updated["id"], {"name": " "})
    with pytest.raises(ValueError, match="engine name already in use"):
        model.update(updated["id"], {"name": "engine-c"})
    with pytest.raises(ValueError, match="provider is required"):
        model.update(updated["id"], {"provider": " "})
    with pytest.raises(ValueError, match="config must be an object"):
        model.update(updated["id"], {"config": []})

    assert model.delete(99999) is False
    assert model.delete(updated["id"]) is True


def test_extractor_registry_model_full_crud_and_filters(core_session_local):
    model = exr_mod.ExtractorRegistryCoreModel(_ctx())

    created = model.create(
        {
            "name": "extract-a",
            "extractor_id": "ext.a",
            "config": {"k": 1},
            "install_config": {"ocr_engine": "rapidocr"},
            "file_extensions": [".txt"],
            "mime_types": ["text/plain"],
            "priority": "2",
            "status": "installed",
            "supported": "1",
        }
    )
    assert created["name"] == "extract-a"
    assert created["priority"] == 2
    assert created["install_config"] == {"ocr_engine": "rapidocr"}

    serialized = model.serialize_row(
        ExtractorRegistry(
            id=7,
            name=None,
            extractor_id=None,
            config=None,
            install_config=None,
            file_extensions=None,
            mime_types=None,
            priority=None,
            status=None,
            supported=0,
        )
    )
    assert serialized["status"] is None
    assert serialized["install_config"] is None
    assert len(model.filters_model()) == 5
    assert len(model.table_model()) == 6

    q = _CollectingQuery()
    model._apply_filters(q, {"name": "a", "extractor_id": "ext", "status": "inst", "id": "1", "supported": "false"})
    assert len(q.filters) == 5

    with pytest.raises(ValueError, match="name and extractor_id are required"):
        model.create({"name": "", "extractor_id": ""})
    with pytest.raises(ValueError, match="config must be an object"):
        model.create({"name": "x", "extractor_id": "id", "config": []})
    with pytest.raises(ValueError, match="install_config must be an object"):
        model.create({"name": "x", "extractor_id": "id", "install_config": []})
    with pytest.raises(ValueError, match="file_extensions must be a list"):
        model.create({"name": "x", "extractor_id": "id", "file_extensions": "txt"})
    with pytest.raises(ValueError, match="mime_types must be a list"):
        model.create({"name": "x", "extractor_id": "id", "mime_types": "m"})
    with pytest.raises(ValueError, match="extractor name already in use"):
        model.create({"name": "extract-a", "extractor_id": "other"})

    assert model.update(999, {"name": "x"}) is None

    updated = model.update(created["id"], {"name": "extract-b", "extractor_id": "ext.b", "config": None, "install_config": {"ocr_engine": "rapidocr"}, "file_extensions": [".md"], "mime_types": ["text/markdown"], "priority": "9", "status": "", "supported": 0})
    assert updated["name"] == "extract-b"
    assert updated["priority"] == 9
    assert updated["status"] == "uninstalled"
    assert updated["install_config"] == {"ocr_engine": "rapidocr"}

    model.create({"name": "extract-c", "extractor_id": "ext.c"})
    with pytest.raises(ValueError, match="name is required"):
        model.update(updated["id"], {"name": " "})
    with pytest.raises(ValueError, match="extractor name already in use"):
        model.update(updated["id"], {"name": "extract-c"})
    with pytest.raises(ValueError, match="extractor_id is required"):
        model.update(updated["id"], {"extractor_id": " "})
    with pytest.raises(ValueError, match="config must be an object"):
        model.update(updated["id"], {"config": []})
    with pytest.raises(ValueError, match="file_extensions must be a list"):
        model.update(updated["id"], {"file_extensions": "bad"})
    with pytest.raises(ValueError, match="mime_types must be a list"):
        model.update(updated["id"], {"mime_types": "bad"})

    assert model.delete(99999) is False
    assert model.delete(updated["id"]) is True


def test_ai_model_usage_model_serialization_and_filters(obs_session_local):
    model = ai_usage_mod.AIModelUsageCoreModel(_ctx())
    with obs_session_local() as session:
        row = AIModelUsageEvent(
            provider="openai",
            model_name="gpt",
            objective="chat",
            request_kind="completion",
            user_id=5,
            total_tokens=100,
            duration_ms=12.5,
            success=1,
            session_id="s",
            request_id="r",
            correlation_id="c",
            engine="eng",
            deployment_mode="local",
            agent_id="a",
            prompt_tokens=40,
            completion_tokens=60,
            error="",
            channel="ws",
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        assert model.serialize_row(row)["success"] is True
        assert model.serialize_detail(row)["prompt_tokens"] == 40

    assert model._default_sort() == ("timestamp", "desc")
    assert len(model.filters_model()) == 6
    assert len(model.table_model()) == 8

    q = _CollectingQuery()
    model._apply_filters(
        q,
        {
            "provider": "oa",
            "model_name": "gpt",
            "objective": "chat",
            "request_kind": "comp",
            "success": "true",
            "user_id": "5",
        },
    )
    assert len(q.filters) == 6

    q_false = _CollectingQuery()
    model._apply_filters(q_false, {"success": "false"})
    assert len(q_false.filters) == 1

    q_bool = _CollectingQuery()
    model._apply_filters(q_bool, {"success": False})
    assert len(q_bool.filters) == 1

    q_bad = _CollectingQuery()
    model._apply_filters(q_bad, {"success": "nope", "user_id": "x"})
    assert q_bad.filters == []


def test_ai_model_pipeline_steps_model_serialization_and_filters(obs_session_local):
    model = ai_steps_mod.AIModelPipelineStepsCoreModel(_ctx())
    with obs_session_local() as session:
        row = AIModelPipelineStep(
            pipeline_id="pipe-1",
            request_id="req-1",
            step_id="step-1",
            root_method="generate_completion",
            type="llm.request",
            name="generate_completion",
            status="ok",
            duration_ms=12.5,
            provider="vllm",
            engine="vllm",
            model_registry_id=7,
            model_name="qwen",
            input_json='{"a": 1}',
            output_json='{"b": 2}',
            stats_json='{"c": 3}',
            metadata_json='{"d": 4}',
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        serialized = model.serialize_row(row)
        assert serialized["pipeline_id"] == "pipe-1"
        assert serialized["duration_ms"] == 12.5
        assert model.serialize_detail(row)["stats_json"] == '{"c": 3}'

    assert model._default_sort() == ("timestamp", "asc")
    assert len(model.filters_model()) == 9
    assert len(model.table_model()) == 9

    q = _CollectingQuery()
    model._apply_filters(
        q,
        {
            "pipeline_id": "pipe-1",
            "request_id": "req-1",
            "type": "llm.request",
            "status": "ok",
            "model_registry_id": 7,
        },
    )
    assert len(q.filters) == 5


def test_model_registry_helpers_and_crud(core_session_local):
    assert mr_mod._normalize_capabilities(None) == ""
    assert mr_mod._normalize_capabilities("chat, vision") == "chat"
    assert mr_mod._normalize_capabilities("embed") == "embedding"
    assert mr_mod._normalize_capabilities(["chat", " ", "vision"]) == "chat"
    assert mr_mod._normalize_capabilities(123) == "123"

    assert mr_mod._serialize_capabilities(None) == []
    assert mr_mod._serialize_capabilities("chat, vision") == ["chat"]

    model = mr_mod.ModelRegistryCoreModel(_ctx())
    with core_session_local() as session:
        eng = _seed_engine(session, name="eng-model")

    with pytest.raises(ValueError, match="name and engine_id are required"):
        model.create({"name": "", "engine_id": None})

    with pytest.raises(ValueError, match="engine_id does not exist"):
        model.create({"name": "m0", "engine_id": 9999})

    created = model.create(
        {
            "name": "m1",
            "engine_id": eng.id,
            "model_path": " /tmp/model ",
            "vram_required_mb": "256",
            "ram_required_mb": "1024",
            "is_downloaded": "1",
            "remote_url": " http://x ",
            "version": " v1 ",
            "capabilities": ["chat", "vision"],
            "extra_config": {"k": 1},
            "status": " installed ",
        }
    )
    assert created["capabilities"] == ["chat"]

    with pytest.raises(ValueError, match="model name already in use"):
        model.create({"name": "m1", "engine_id": eng.id})

    assert len(model.filters_model()) == 7
    assert len(model.table_model()) == 7

    q = _CollectingQuery()
    model._apply_filters(q, {"name": "m", "status": "inst", "capabilities": "chat", "id": "1", "engine_id": "1", "is_downloaded": "1"})
    assert len(q.filters) == 6

    assert model.update(999, {"name": "x"}) is None

    model2 = model.create({"name": "m2", "engine_id": eng.id})
    with pytest.raises(ValueError, match="name is required"):
        model.update(created["id"], {"name": " "})
    with pytest.raises(ValueError, match="model name already in use"):
        model.update(created["id"], {"name": "m2"})
    with pytest.raises(ValueError, match="engine_id is required"):
        model.update(created["id"], {"engine_id": "bad"})
    with pytest.raises(ValueError, match="engine_id does not exist"):
        model.update(created["id"], {"engine_id": 9876})

    updated = model.update(
        created["id"],
        {
            "model_path": "",
            "vram_required_mb": None,
            "ram_required_mb": None,
            "is_downloaded": 0,
            "remote_url": "",
            "version": "",
            "capabilities": "chat,reasoning",
            "extra_config": [],
            "status": "",
        },
    )
    assert updated["model_path"] is None
    assert updated["remote_url"] is None
    assert updated["version"] is None
    assert updated["extra_config"] is None
    assert updated["vram_required_mb"] == 0
    assert updated["status"] == "available"

    assert model.delete(999) is False
    assert model.delete(model2["id"]) is True


def test_objective_mappings_model_crud_and_filters(core_session_local):
    model = om_mod.ObjectiveMappingsCoreModel(_ctx())

    with core_session_local() as session:
        eng = _seed_engine(session, name="eng-obj")
        m1 = _seed_model(session, eng.id, name="obj-model-1")
        m2 = _seed_model(session, eng.id, name="obj-model-2")

    with pytest.raises(ValueError, match="objective and model_id are required"):
        model.create({"objective": "", "model_id": None})
    with pytest.raises(ValueError, match="model_id does not exist"):
        model.create({"objective": "chat", "model_id": 99999})

    created = model.create({"objective": "chat", "model_id": m1.id})
    assert created["objective"] == "chat"

    with pytest.raises(ValueError, match="objective already mapped"):
        model.create({"objective": "chat", "model_id": m2.id})

    assert len(model.filters_model()) == 3
    assert len(model.table_model()) == 3

    q = _CollectingQuery()
    model._apply_filters(q, {"objective": "cha", "id": str(created["id"]), "model_id": str(m1.id)})
    assert len(q.filters) == 3

    assert model.update(999, {"objective": "x"}) is None

    with pytest.raises(ValueError, match="objective is required"):
        model.update(created["id"], {"objective": " "})
    with pytest.raises(ValueError, match="model_id is required"):
        model.update(created["id"], {"model_id": "bad"})
    with pytest.raises(ValueError, match="model_id does not exist"):
        model.update(created["id"], {"model_id": 88888})

    second = model.create({"objective": "vision", "model_id": m2.id})
    with pytest.raises(ValueError, match="objective already mapped"):
        model.update(second["id"], {"objective": "chat"})

    updated = model.update(created["id"], {"model_id": m2.id})
    assert updated["model_id"] == m2.id

    assert model.delete(9999) is False
    assert model.delete(second["id"]) is True


def test_model_capability_priority_model_crud_and_filters(core_session_local):
    assert normalize_capability(None) == ""
    assert normalize_capability(" Chat ") == "chat"

    model = mcp_mod.ModelCapabilityPriorityCoreModel(_ctx())

    with core_session_local() as session:
        eng = _seed_engine(session, name="eng-cap")
        m1 = _seed_model(session, eng.id, name="cap-model-1")
        m2 = _seed_model(session, eng.id, name="cap-model-2")

    with pytest.raises(ValueError, match="capability, model_id and priority are required"):
        model.create({"capability": "", "model_id": None, "priority": None})
    with pytest.raises(ValueError, match="priority must be >= 1"):
        model.create({"capability": "chat", "model_id": m1.id, "priority": 0})
    with pytest.raises(ValueError, match="model_id does not exist"):
        model.create({"capability": "chat", "model_id": 9999, "priority": 1})

    created = model.create({"capability": "chat", "model_id": m1.id, "priority": 1})
    assert created["capability"] == "chat"

    with pytest.raises(ValueError, match="capability/model pair already exists"):
        model.create({"capability": "chat", "model_id": m1.id, "priority": 2})
    with pytest.raises(ValueError, match="priority already assigned for capability"):
        model.create({"capability": "chat", "model_id": m2.id, "priority": 1})

    assert len(model.filters_model()) == 4
    assert len(model.table_model()) == 4

    q = _CollectingQuery()
    model._apply_filters(q, {"capability": "chat", "id": str(created["id"]), "model_id": str(m1.id), "priority": "1"})
    assert len(q.filters) == 4

    assert model.update(99999, {"priority": 2}) is None

    with pytest.raises(ValueError, match="capability is required"):
        model.update(created["id"], {"capability": " "})
    with pytest.raises(ValueError, match="model_id is required"):
        model.update(created["id"], {"model_id": "bad"})
    with pytest.raises(ValueError, match="model_id does not exist"):
        model.update(created["id"], {"model_id": 88888})
    with pytest.raises(ValueError, match="priority is required"):
        model.update(created["id"], {"priority": "bad"})
    with pytest.raises(ValueError, match="priority must be >= 1"):
        model.update(created["id"], {"priority": 0})

    second = model.create({"capability": "chat", "model_id": m2.id, "priority": 2})
    with pytest.raises(ValueError, match="capability/model pair already exists"):
        model.update(second["id"], {"model_id": m1.id})
    with pytest.raises(ValueError, match="priority already assigned for capability"):
        model.update(second["id"], {"priority": 1})

    updated = model.update(created["id"], {"capability": "image_to_text", "model_id": m2.id, "priority": 3})
    assert updated["capability"] == "image_to_text"
    assert updated["priority"] == 3

    assert model.delete(999) is False
    assert model.delete(second["id"]) is True


def test_ai_selection_config_models_do_not_refresh_engine_orchestrator(
    core_session_local,
    monkeypatch,
):
    monkeypatch.setattr(er_mod, "_request_os_allowlist_refresh", lambda **_kwargs: None)

    engine_model = er_mod.EngineRegistryCoreModel(_ctx())
    model_registry = mr_mod.ModelRegistryCoreModel(_ctx())
    objective_mappings = om_mod.ObjectiveMappingsCoreModel(_ctx())
    priority_model = mcp_mod.ModelCapabilityPriorityCoreModel(_ctx())

    engine = engine_model.create(
        {
            "name": "refresh-test-engine",
            "provider": "refresh_provider",
            "config": {},
            "status": "active",
            "supported": True,
        }
    )
    model = model_registry.create(
        {
            "name": "refresh-test-model",
            "engine_id": engine["id"],
            "status": "active",
            "capabilities": ["chat"],
        }
    )
    objective = objective_mappings.create(
        {"objective": "refresh-test-objective", "model_id": model["id"]}
    )
    priority = priority_model.create(
        {"capability": "chat", "model_id": model["id"], "priority": 1}
    )

    engine_model.update(engine["id"], {"config": {"concurrency_enabled": True}})
    model_registry.update(model["id"], {"status": "active"})
    objective_mappings.update(objective["id"], {"objective": "refresh-test-objective-2"})
    priority_model.update(priority["id"], {"priority": 2})

    assert priority_model.delete(priority["id"]) is True
    assert objective_mappings.delete(objective["id"]) is True
    assert model_registry.delete(model["id"]) is True
    assert engine_model.delete(engine["id"]) is True


def test_module_locks_model_crud_and_filters(core_session_local):
    model = ml_mod.ModuleLocksCoreModel(_ctx())

    with pytest.raises(ValueError, match="module_name is required"):
        model.create({"module_name": " "})
    with pytest.raises(ValueError, match="at least one scope id is required"):
        model.create({"module_name": "system"})

    created = model.create({"module_name": "system", "user_id": 1})
    assert created["module_name"] == "system"

    assert len(model.filters_model()) == 5
    assert len(model.table_model()) == 7

    fake = ModuleLock(id=1, module_name="x", user_id=None, organization_id=None, role_id=None)
    assert model.serialize_row(fake)["user_id"] is None

    q = _CollectingQuery()
    model._apply_filters(q, {"module_name": "sys", "id": "1", "user_id": "1", "organization_id": "2", "role_id": "3"})
    assert len(q.filters) == 5

    assert model.update(999, {"module_name": "x"}) is None
    with pytest.raises(ValueError, match="module_name is required"):
        model.update(created["id"], {"module_name": " "})

    updated = model.update(created["id"], {"module_name": "system2", "organization_id": 7, "role_id": 2, "user_id": None})
    assert updated["module_name"] == "system2"
    assert updated["organization_id"] == 7

    assert model.delete(9999) is False
    assert model.delete(created["id"]) is True


def test_roles_model_full_paths(core_session_local):
    model = roles_mod.RolesCoreModel(_ctx())

    assert len(model.form_model_create()) == 3
    assert model.form_model_update(1) == model.form_model_create()

    with core_session_local() as session:
        session.add_all([Permission(name="z.perm"), Permission(name="a.perm"), Permission(name="")])
        session.commit()

    assert model.form_model_extra("unknown") == []
    options = model.form_model_extra("permissions_options")
    assert options == [{"label": "a.perm", "value": "a.perm"}, {"label": "z.perm", "value": "z.perm"}]

    with pytest.raises(ValueError, match="role name is required"):
        model.create({"name": " "})

    created = model.create({"name": "editor", "description": "desc", "permissions": ["perm.read", "", "perm.write"]})
    assert created["permissions_count"] == 2

    with pytest.raises(ValueError, match="role name already in use"):
        model.create({"name": "editor"})

    assert len(model.filters_model()) == 4
    assert len(model.table_model()) == 4

    q = _CollectingQuery()
    model._apply_filters(q, {"name": "ed", "description": "de", "permission": "perm", "id": str(created["id"])})
    assert len(q.filters) == 4

    assert model.update(999, {"name": "x"}) is None

    super_role = model.create({"name": "super"})
    with pytest.raises(ValueError, match="super role cannot be modified or deleted"):
        model.update(super_role["id"], {"description": "x"})

    with pytest.raises(ValueError, match="role name is required"):
        model.update(created["id"], {"name": " "})

    model.create({"name": "manager"})
    with pytest.raises(ValueError, match="role name already in use"):
        model.update(created["id"], {"name": "manager"})

    updated = model.update(created["id"], {"name": "editor2", "description": "", "permissions": "bad"})
    assert updated["name"] == "editor2"
    assert updated["permissions"] == []

    assert model.delete(9999) is False
    with pytest.raises(ValueError, match="super role cannot be modified or deleted"):
        model.delete(super_role["id"])
    assert model.delete(created["id"]) is True


def test_users_model_full_paths(core_session_local, monkeypatch):
    monkeypatch.setattr(users_mod, "get_hashed_password", lambda password: f"hash::{password}")
    monkeypatch.setattr(users_mod, "core_verify_user", lambda username, password: (username == "u" and password == "p", None))
    monkeypatch.setattr(users_mod, "get_user_access_profile_by_username", lambda username: {"username": username})
    monkeypatch.setattr(users_mod, "get_user_access_profile", lambda user_id: {"id": user_id})

    model = users_mod.UsersCoreModel(_ctx())

    assert model.verify("u", "p") is True
    assert model.verify("u", "bad") is False
    assert model.get_info("name") == {"username": "name"}
    assert model.get_info_by_id(8) == {"id": 8}

    assert len(model.form_model_create()) == 7
    assert len(model.form_model_update(1)) == 5

    with core_session_local() as session:
        role_admin = Role(name="admin")
        role_viewer = Role(name="viewer")
        session.add_all([role_admin, role_viewer])
        session.commit()

    with pytest.raises(ValueError, match="username and password are required"):
        model.create({"username": "", "password": ""})

    created = model.create(
        {
            "username": "alice",
            "password": "pw",
            "email": "alice@example.com",
            "role": "admin",
            "access_level": ROLE_LEVEL_ORGANIZATION,
            "organization_id": 42,
        }
    )
    assert created["username"] == "alice"
    assert created["roles"] == ["admin"]

    with pytest.raises(ValueError, match="username already in use"):
        model.create({"username": "alice", "password": "pw2"})

    assert len(model.filters_model()) == 8
    assert len(model.table_model()) == 8

    q = _CollectingQuery()
    model._apply_filters(
        q,
        {
            "username": "ali",
            "email": "example",
            "language": "en",
            "role": "adm",
            "id": str(created["id"]),
            "access_level": str(ROLE_LEVEL_ORGANIZATION),
            "organization_id": "42",
        },
    )
    assert len(q.filters) == 7

    # Covers serialize_row branch without roles and with created_at missing.
    row = User(id=99, username="u", email=None, language=None, access_level=None, organization_id=None)
    assert model.serialize_row(row)["role"] is None

    assert model.update(99999, {"username": "x"}) is None

    with pytest.raises(ValueError, match="username is required"):
        model.update(created["id"], {"username": " "})

    model.create({"username": "bob", "password": "pw", "role": "viewer"})
    with pytest.raises(ValueError, match="username already in use"):
        model.update(created["id"], {"username": "bob"})

    updated = model.update(
        created["id"],
        {
            "email": "",
            "language": " IT ",
            "access_level": str(ROLE_LEVEL_USER),
            "organization_id": "77",
            "role": "viewer",
            "password": "newpw",
        },
    )
    assert updated["email"] is None
    assert updated["language"] == "it"
    assert updated["roles"] == ["viewer"]

    unchanged = model.update(created["id"], {"role": "missing"})
    assert unchanged is not None

    assert model.delete(999999) is False
    assert model.delete(created["id"]) is True


def test_entities_branch_closure_paths(core_session_local, obs_session_local, monkeypatch):
    monkeypatch.setattr(er_mod, "_request_os_allowlist_refresh", lambda **_kwargs: None)
    # background_tasks: cover numeric filters None -> continue path
    bg_model = bg_mod.BackgroundTasksCoreModel(_ctx())
    q_bg = _CollectingQuery()
    bg_model._apply_filters(q_bg, {"user_id": None, "organization_id": None})
    assert q_bg.filters == []

    # audit_events: actor_user_id missing branch
    audit_model = audit_mod.AuditEventsCoreModel(_ctx())
    q_audit = _CollectingQuery()
    audit_model._apply_filters(q_audit, {"event_type": 123})
    assert q_audit.filters == []

    # node registries: raw_id None branch
    q_en = _CollectingQuery()
    enir_mod.EngineNodeInstallRegistryCoreModel(_ctx())._apply_filters(q_en, {})
    assert q_en.filters == []
    q_exn = _CollectingQuery()
    exnir_mod.ExtractorNodeInstallRegistryCoreModel(_ctx())._apply_filters(q_exn, {})
    assert q_exn.filters == []

    # ai_model_usage: success None and non-bool/non-str branches
    ai_usage_model = ai_usage_mod.AIModelUsageCoreModel(_ctx())
    q_ai_usage_1 = _CollectingQuery()
    ai_usage_model._apply_filters(q_ai_usage_1, {"provider": 1})
    assert q_ai_usage_1.filters == []
    q_ai_usage_2 = _CollectingQuery()
    ai_usage_model._apply_filters(q_ai_usage_2, {"success": 1})
    assert q_ai_usage_2.filters == []

    # engine/extractor registry _apply_filters false-paths
    q_er = _CollectingQuery()
    er_mod.EngineRegistryCoreModel(_ctx())._apply_filters(
        q_er, {"name": 1, "provider": 2, "status": 3, "id": "bad"}
    )
    assert q_er.filters == []
    q_exr = _CollectingQuery()
    exr_mod.ExtractorRegistryCoreModel(_ctx())._apply_filters(
        q_exr, {"name": 1, "extractor_id": 2, "status": 3, "id": "bad"}
    )
    assert q_exr.filters == []

    er_model = er_mod.EngineRegistryCoreModel(_ctx())
    er_item = er_model.create({"name": "eng-branch", "provider": "p"})
    er_up = er_model.update(er_item["id"], {"provider": "p2"})
    assert er_up["provider"] == "p2"

    exr_model = exr_mod.ExtractorRegistryCoreModel(_ctx())
    exr_item = exr_model.create({"name": "ext-branch", "extractor_id": "ext.branch"})
    exr_up = exr_model.update(exr_item["id"], {"extractor_id": "ext.branch.2"})
    assert exr_up["extractor_id"] == "ext.branch.2"

    # model_capability_priority _apply_filters continue
    q_mcp = _CollectingQuery()
    mcp_mod.ModelCapabilityPriorityCoreModel(_ctx())._apply_filters(
        q_mcp, {"id": "x", "model_id": None, "priority": object()}
    )
    assert q_mcp.filters == []

    # module_locks: parsed None continue + update false-path branches
    ml_model = ml_mod.ModuleLocksCoreModel(_ctx())
    q_ml = _CollectingQuery()
    ml_model._apply_filters(
        q_ml,
        {"module_name": 10, "id": "x", "user_id": "x", "organization_id": "x", "role_id": "x"},
    )
    assert q_ml.filters == []
    lock = ml_model.create({"module_name": "mlock", "user_id": 2})
    unchanged_lock = ml_model.update(lock["id"], {})
    assert unchanged_lock is not None

    # objective_mappings: objective non-str + parsed None + objective assignment branch
    om_model = om_mod.ObjectiveMappingsCoreModel(_ctx())
    with core_session_local() as session:
        eng = _seed_engine(session, name="eng-obj-branch")
        m1 = _seed_model(session, eng.id, name="obj-branch-1")
        m2 = _seed_model(session, eng.id, name="obj-branch-2")
    q_om = _CollectingQuery()
    om_model._apply_filters(q_om, {"objective": 1, "id": "x", "model_id": None})
    assert q_om.filters == []
    obj = om_model.create({"objective": "obj-x", "model_id": m1.id})
    obj_up = om_model.update(obj["id"], {"objective": "obj-y"})
    assert obj_up["objective"] == "obj-y"
    obj_up2 = om_model.update(obj["id"], {"model_id": m2.id})
    assert obj_up2["model_id"] == m2.id

    # model_registry: false-path filter continues + explicit name/engine assignment branches
    mr_model = mr_mod.ModelRegistryCoreModel(_ctx())
    with core_session_local() as session:
        e1 = _seed_engine(session, name="eng-mr-1")
        e2 = _seed_engine(session, name="eng-mr-2")
    q_mr = _CollectingQuery()
    mr_model._apply_filters(q_mr, {"name": 1, "status": 2, "capabilities": 3, "id": "x", "engine_id": "x", "is_downloaded": "x"})
    assert q_mr.filters == []
    m = mr_model.create({"name": "mr-model", "engine_id": e1.id})
    m_up = mr_model.update(m["id"], {"name": "mr-model-2", "engine_id": e2.id})
    assert m_up["name"] == "mr-model-2"
    assert m_up["engine_id"] == e2.id

    # roles: invalid role_id filter path + create permissions non-list path + skip branches in update
    roles_model = roles_mod.RolesCoreModel(_ctx())
    q_roles = _CollectingQuery()
    roles_model._apply_filters(q_roles, {"name": 1, "description": 2, "permission": 3, "id": "bad"})
    assert q_roles.filters == []
    q_roles_none = _CollectingQuery()
    roles_model._apply_filters(q_roles_none, {})
    assert q_roles_none.filters == []
    with core_session_local() as session:
        session.add(Permission(name="perm.preexisting"))
        session.commit()
    role_existing_perm = roles_model.create({"name": "branch-role-existing-perm", "permissions": ["perm.preexisting"]})
    assert "perm.preexisting" in role_existing_perm["permissions"]
    role = roles_model.create({"name": "branch-role", "permissions": "bad"})
    assert role["permissions"] == []
    role_up = roles_model.update(role["id"], {"description": "d1"})
    assert role_up["description"] == "d1"
    role_up2 = roles_model.update(role["id"], {"permissions": ["perm.branch"]})
    assert "perm.branch" in role_up2["permissions"]

    # users: continue branches in filters + create without role + username assignment branch
    monkeypatch.setattr(users_mod, "get_hashed_password", lambda password: f"h::{password}")
    users_model = users_mod.UsersCoreModel(_ctx())
    q_users = _CollectingQuery()
    users_model._apply_filters(
        q_users,
        {
            "username": 1,
            "email": 2,
            "language": 3,
            "role": 4,
            "id": None,
            "access_level": "bad",
            "organization_id": "bad",
        },
    )
    assert q_users.filters == []
    usr = users_model.create({"username": "branch-user", "password": "pw"})
    assert usr["roles"] == []
    usr_up = users_model.update(usr["id"], {"username": "branch-user-2", "access_level": "bad"})
    assert usr_up["username"] == "branch-user-2"

    # observability-backed models: keep obs fixture active and touch read operations with success None.
    with obs_session_local() as session:
        session.add(AIModelUsageEvent(provider="p", model_name="m", request_kind="rk", success=1))
        session.commit()
