from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace

import pytest

import democrai.core.infrastructure.sandbox.os.bootstrap as os_sandbox_bootstrap_mod
import democrai.core.infrastructure.sandbox.os.core_relaunch as core_relaunch_mod
import democrai.core.runtime.bootstrap.bootstrap_pipeline as pipeline_mod
import democrai.core.runtime.bootstrap.bootstrap_pipeline_helpers as helpers_mod


def test_helpers_init_modules(monkeypatch):
    calls = []
    modules = SimpleNamespace(
        configure_trust=lambda **kwargs: calls.append(("trust", kwargs)),
        enable_runtime=lambda: calls.append(("enable", None)),
        discover_modules=lambda path, is_builtin, load_ui: calls.append(("discover", path, is_builtin, load_ui)),
    )
    cfg = SimpleNamespace(
        get=lambda key, default=None: {
            "modules.trust_mode": "trusted_only",
            "modules.allow_user_modules": None,
            "modules.trusted_modules": "a,b",
        }.get(key, default)
    )
    logger_calls = []
    ctx_mod = SimpleNamespace(config=cfg, modules=modules, logger=SimpleNamespace(info=lambda *a, **k: logger_calls.append(a)))
    monkeypatch.setattr(helpers_mod, "get_runtime_module_dirs", lambda: ("/runtime/modules",))

    helpers_mod.init_modules(ctx_mod, args=SimpleNamespace())
    assert calls[0][0] == "trust"
    assert calls[0][1]["allow_user_modules"] is False
    assert any(item[0] == "discover" and item[2] is True for item in calls)

    calls.clear()
    cfg_runtime = SimpleNamespace(
        get=lambda key, default=None: {
            "modules.trust_mode": "all",
            "modules.allow_user_modules": True,
            "modules.trusted_modules": [],
        }.get(key, default)
    )
    ctx_runtime = SimpleNamespace(
        config=cfg_runtime,
        modules=modules,
        logger=SimpleNamespace(info=lambda *a, **k: None),
    )
    helpers_mod.init_modules(
        ctx_runtime,
        args=SimpleNamespace(module_paths=("/runtime/modules",)),
    )
    assert ("discover", "/runtime/modules", True, True) in calls

    calls.clear()
    helpers_mod.init_modules(
        ctx_runtime,
        args=SimpleNamespace(module_paths=("/runtime/modules",)),
        load_ui=False,
    )
    assert ("discover", "/runtime/modules", True, False) in calls


def test_helpers_init_knowledge_leaves_legacy_runtime_unconfigured(monkeypatch):
    ctx = SimpleNamespace(
        config=SimpleNamespace(get=lambda key, default=None: default),
        db=SimpleNamespace(get_session=lambda: object()),
        vector_store=object(),
        kg_store=object(),
        logger=SimpleNamespace(info=lambda *a, **k: None),
    )

    monkeypatch.setattr(
        helpers_mod,
        "get_knowledge_runtime_config",
        lambda: {"enabled": False},
    )
    helpers_mod.init_knowledge(ctx)
    assert ctx.knowledge_service is None
    assert ctx.knowledge_ingestion is None
    assert ctx.knowledge_runtime is None


def test_reload_knowledge_runtime_stops_and_clears_disabled_runtime(monkeypatch):
    from democrai.core.application.knowledge import runtime_reload

    calls = []
    old_runtime = SimpleNamespace(stop=lambda: calls.append("stop-old"))
    ctx = SimpleNamespace(
        setup_mode=False,
        knowledge_service=object(),
        knowledge_ingestion=object(),
        knowledge_runtime=old_runtime,
    )

    def _init_knowledge(resolved_ctx):
        calls.append("init")
        resolved_ctx.knowledge_service = None
        resolved_ctx.knowledge_ingestion = None
        resolved_ctx.knowledge_runtime = None

    monkeypatch.setattr(helpers_mod, "init_knowledge", _init_knowledge)

    runtime_reload.reload_knowledge_runtime(ctx)

    assert calls == ["stop-old", "init"]
    assert ctx.knowledge_service is None
    assert ctx.knowledge_ingestion is None
    assert ctx.knowledge_runtime is None


def test_reload_knowledge_runtime_rebuilds_and_starts_enabled_runtime(monkeypatch):
    from democrai.core.application.knowledge import runtime_reload

    calls = []
    old_runtime = SimpleNamespace(stop=lambda: calls.append("stop-old"))
    new_runtime = SimpleNamespace(start=lambda: calls.append("start-new"))
    ctx = SimpleNamespace(
        setup_mode=False,
        knowledge_service=object(),
        knowledge_ingestion=object(),
        knowledge_runtime=old_runtime,
    )

    def _init_knowledge(resolved_ctx):
        calls.append("init")
        resolved_ctx.knowledge_service = object()
        resolved_ctx.knowledge_ingestion = object()
        resolved_ctx.knowledge_runtime = new_runtime

    monkeypatch.setattr(helpers_mod, "init_knowledge", _init_knowledge)

    runtime_reload.reload_knowledge_runtime(ctx)

    assert calls == ["stop-old", "init", "start-new"]
    assert ctx.knowledge_runtime is new_runtime


def test_reload_knowledge_runtime_is_noop_in_setup_mode(monkeypatch):
    from democrai.core.application.knowledge import runtime_reload

    calls = []
    runtime = SimpleNamespace(stop=lambda: calls.append("stop"))
    ctx = SimpleNamespace(setup_mode=True, knowledge_runtime=runtime)

    monkeypatch.setattr(helpers_mod, "init_knowledge", lambda _ctx: calls.append("init"))

    runtime_reload.reload_knowledge_runtime(ctx)

    assert calls == []
    assert ctx.knowledge_runtime is runtime


def test_helpers_knowledge_triple_config_uses_model_extra_config_only():
    row = SimpleNamespace(
        extra_config={
            "defaults": {
                "runtime": {
                    "max_entities": 7,
                    "max_relations": 11,
                    "temperature": 0.2,
                    "max_tokens": 512,
                    "ignored": "value",
                }
            },
            "ignored": "value",
        }
    )

    assert helpers_mod._knowledge_triple_extractor_config(row) == {
        "max_entities": 7,
        "max_relations": 11,
        "temperature": 0.2,
        "max_tokens": 512,
    }
    assert helpers_mod._knowledge_triple_extractor_config(
        SimpleNamespace(extra_config=None)
    ) == {}


def test_helpers_module_policy_branches(monkeypatch):
    calls = []
    modules = SimpleNamespace(
        configure_trust=lambda **kwargs: calls.append(("trust", kwargs)),
        enable_runtime=lambda: calls.append(("enable", None)),
        discover_modules=lambda path, is_builtin, load_ui: calls.append(
            ("discover", path, is_builtin, load_ui)
        ),
    )
    ctx_mod = SimpleNamespace(
        config=SimpleNamespace(
            get=lambda key, default=None: {
                "modules.trust_mode": "all",
                "modules.allow_user_modules": "off",
                "modules.trusted_modules": None,
            }.get(key, default)
        ),
        modules=modules,
        logger=SimpleNamespace(info=lambda *a, **k: calls.append(("log", a))),
    )
    monkeypatch.setattr(helpers_mod, "get_runtime_module_dirs", lambda: ("/runtime/modules",))
    helpers_mod.init_modules(ctx_mod, args=SimpleNamespace())
    assert calls[0][1]["allow_user_modules"] is False
    assert calls[0][1]["trusted_modules"] == []
    assert not any(item[0] == "discover" and item[2] is False for item in calls)

    calls2 = []
    ctx_mod2 = SimpleNamespace(
        config=SimpleNamespace(
            get=lambda key, default=None: {
                "modules.trust_mode": "trusted_only",
                "modules.allow_user_modules": "unexpected",
                "modules.trusted_modules": ["a", " ", "b"],
            }.get(key, default)
        ),
        modules=SimpleNamespace(
            configure_trust=lambda **kwargs: calls2.append(("trust", kwargs)),
            enable_runtime=lambda: None,
            discover_modules=lambda *a, **k: calls2.append(("discover", a, k)),
        ),
        logger=SimpleNamespace(info=lambda *a, **k: None),
    )
    helpers_mod.init_modules(ctx_mod2, args=SimpleNamespace())
    assert calls2[0][1]["trusted_modules"] == ["a", "b"]
    assert calls2[0][1]["allow_user_modules"] is False

    # allow_user_modules true branch (discover user modules)
    calls3 = []
    ctx_mod3 = SimpleNamespace(
        config=SimpleNamespace(
            get=lambda key, default=None: {
                "modules.trust_mode": "all",
                "modules.allow_user_modules": "yes",
                "modules.trusted_modules": [],
            }.get(key, default)
        ),
        modules=SimpleNamespace(
            configure_trust=lambda **kwargs: calls3.append(("trust", kwargs)),
            enable_runtime=lambda: None,
            discover_modules=lambda path, is_builtin, load_ui: calls3.append(
                ("discover", path, is_builtin, load_ui)
            ),
        ),
        logger=SimpleNamespace(info=lambda *a, **k: None),
    )
    helpers_mod.init_modules(ctx_mod3, args=SimpleNamespace())
    assert any(item[0] == "discover" and item[2] is False for item in calls3)


def test_pipeline_runtime_bootstrapper_core_paths(monkeypatch):
    logger = SimpleNamespace(info=lambda *a, **k: None, warning=lambda *a, **k: None, error=lambda *a, **k: None, debug=lambda *a, **k: None)
    ctx = SimpleNamespace(logger=logger, setup_mode=False)
    monkeypatch.setattr(pipeline_mod, "app_ctx", lambda: ctx)

    order = []
    b = pipeline_mod.RuntimeBootstrapper()
    b.init_config = lambda _ctx: order.append("config")
    b.configure_logging = lambda _ctx: order.append("logging")
    b.ensure_core_os_sandbox_relaunched = lambda _ctx, _args: order.append("relaunch")
    b.refresh_os_network_allowlist = lambda _ctx: order.append("allow")
    b.init_storage = lambda _ctx: order.append("storage")
    b.sync_engine_registry = lambda _ctx: order.append("engine-reg")
    def _init_network(_ctx, _args):
        order.append("network")
        ctx.network = SimpleNamespace(
            start=lambda: order.append("network-start"),
            core=SimpleNamespace(
                session_service=SimpleNamespace(
                    start_cleanup_loop=lambda: order.append("cleanup-loop")
                )
            ),
            init_http_ws=lambda *a, **k: order.append("http"),
            _loop=None,
        )
    b.init_network = _init_network
    b.init_modules = lambda _ctx, _args: (order.append("modules"), setattr(ctx, "modules", SimpleNamespace(schedule_startup=lambda loop: order.append("startup"))))
    b.warmup_routing = lambda _ctx, _args: order.append("warmup")
    b.process_deferred_external_access_resumes = lambda _ctx: order.append("deferred-resume")
    b.acquire_background_services_lock = lambda _ctx: True
    b.run_migrations = lambda _ctx, **_kwargs: order.append("migrations")
    b.sync_extractor_registry = lambda _ctx: order.append("extractor-reg")
    b.start_runtime_prompt_grpc_runtime = lambda _ctx: order.append("runtime-prompt")
    b.start_engine_orchestrator_runtime = lambda _ctx: order.append("engine-orchestrator")
    b.start_knowledge_query_runtime = lambda _ctx: order.append("knowledge-query")
    b.start_setup_finalize_runtime = lambda _ctx: order.append("setup-finalize")
    b.start_environment_runtime = lambda _ctx: order.append("environment")
    b.start_os_allowlist_runtime = lambda _ctx: order.append("os-allowlist")
    b.start_engine_install_runtime = lambda _ctx: order.append("engine-runtime")
    b.start_extractor_install_runtime = lambda _ctx: order.append("extractor-runtime")
    b.start_runtime_metrics_runtime = lambda _ctx: order.append("runtime-metrics")
    b.start_knowledge_extraction_queue_runtime = lambda _ctx: order.append("knowledge-extraction")
    b.start_knowledge_runtime = lambda _ctx: order.append("knowledge-runtime")
    b.ipc_endpoint = lambda _ctx: "ipc-endpoint"

    args = SimpleNamespace(mode="desktop", http=False, host="127.0.0.1", port=9000, listen_fd=None)
    assert b.bootstrap(args) == "ipc-endpoint"
    assert order[:6] == ["config", "logging", "relaunch", "allow", "storage", "engine-reg"]
    assert "deferred-resume" in order
    assert "http" in order

    # failure path after network start
    stop_calls = []
    ctx2 = SimpleNamespace(logger=logger, setup_mode=False, network=SimpleNamespace(stop=lambda: stop_calls.append("stopped")))
    monkeypatch.setattr(pipeline_mod, "app_ctx", lambda: ctx2)
    b2 = pipeline_mod.RuntimeBootstrapper()
    b2.init_config = lambda _ctx: None
    b2.configure_logging = lambda _ctx: None
    b2.ensure_core_os_sandbox_relaunched = lambda _ctx, _args: None
    b2.refresh_os_network_allowlist = lambda _ctx: None
    b2.init_storage = lambda _ctx: None
    b2.sync_engine_registry = lambda _ctx: None
    b2.init_network = lambda _ctx, _args: None
    b2.init_modules = lambda _ctx, _args: None
    b2.sync_environment_definitions = lambda _ctx: None
    b2.warmup_routing = lambda _ctx, _args: None
    b2.process_deferred_external_access_resumes = lambda _ctx: None
    b2.acquire_background_services_lock = lambda _ctx: True
    b2.run_migrations = lambda _ctx, **_kwargs: None
    b2.sync_extractor_registry = lambda _ctx: None
    b2.apply_environment_variables = lambda _ctx: None
    b2.start_core_reloader = lambda _ctx, _args: None
    b2.start_runtime_prompt_grpc_runtime = lambda _ctx: None
    b2.start_engine_orchestrator_runtime = lambda _ctx: None
    b2.start_knowledge_query_runtime = lambda _ctx: None
    b2.start_setup_finalize_runtime = lambda _ctx: None
    b2.start_environment_runtime = lambda _ctx: None
    b2.start_os_allowlist_runtime = lambda _ctx: None
    b2.start_engine_install_runtime = lambda _ctx: None
    b2.start_extractor_install_runtime = lambda _ctx: None
    b2.start_runtime_metrics_runtime = lambda _ctx: None
    b2.start_knowledge_extraction_queue_runtime = lambda _ctx: None
    b2.start_knowledge_runtime = lambda _ctx: (_ for _ in ()).throw(RuntimeError("boom"))
    ctx2.network.start = lambda: None
    ctx2.network.core = SimpleNamespace(session_service=SimpleNamespace(start_cleanup_loop=lambda: None))
    ctx2.modules = SimpleNamespace(schedule_startup=lambda loop: None)
    ctx2.network.init_http_ws = lambda *a, **k: None
    with pytest.raises(RuntimeError):
        b2.bootstrap(SimpleNamespace(mode="server", http=False, host="h", port=1, listen_fd=None))
    assert stop_calls == ["stopped"]


def test_pipeline_misc_methods(monkeypatch, tmp_path):
    logger_calls = {"warn": [], "info": [], "err": [], "dbg": []}
    logger = SimpleNamespace(
        warning=lambda *a, **k: logger_calls["warn"].append(a),
        info=lambda *a, **k: logger_calls["info"].append(a),
        error=lambda *a, **k: logger_calls["err"].append(a),
        debug=lambda *a, **k: logger_calls["dbg"].append(a),
    )
    b = pipeline_mod.RuntimeBootstrapper()

    # sync registries
    called = []
    monkeypatch.setitem(sys.modules, "democrai.core.application.ai.engine.manifests", SimpleNamespace(sync_engine_manifests_to_registry=lambda: called.append("eng")))
    monkeypatch.setitem(sys.modules, "democrai.core.application.knowledge.extractor.manifests", SimpleNamespace(sync_extractor_manifests_to_registry=lambda: called.append("ext")))
    b.sync_engine_registry(SimpleNamespace(setup_mode=False))
    b.sync_engine_registry(SimpleNamespace(setup_mode=True))
    b.sync_extractor_registry(SimpleNamespace(setup_mode=False, logger=logger))
    b.sync_extractor_registry(SimpleNamespace(setup_mode=True, logger=logger))
    assert "eng" in called and "ext" in called

    monkeypatch.setitem(sys.modules, "democrai.core.application.knowledge.extractor.manifests", SimpleNamespace(sync_extractor_manifests_to_registry=lambda: (_ for _ in ()).throw(RuntimeError("x"))))
    b.sync_extractor_registry(SimpleNamespace(setup_mode=False, logger=logger))
    assert logger_calls["warn"]

    # allowlist refresh branches
    monkeypatch.setattr(os_sandbox_bootstrap_mod, "debug_os_sandbox_flow", lambda *a, **k: logger_calls["info"].append(a))
    b.refresh_os_network_allowlist(SimpleNamespace(setup_mode=True, config={}))

    monkeypatch.setitem(sys.modules, "democrai.core.infrastructure.sandbox.os.state", SimpleNamespace(is_application_network_allowlist_enabled=lambda _cfg: False, set_application_network_allowlist_active=lambda _v: None))
    monkeypatch.setitem(sys.modules, "democrai.core.infrastructure.sandbox.os.events", SimpleNamespace(register_os_sandbox_event_listeners=lambda: None, emit_application_network_allowlist_refresh_event=lambda payload=None: asyncio.sleep(0)))
    monkeypatch.setitem(sys.modules, "democrai.core.infrastructure.sandbox.os.helper", SimpleNamespace(ensure_os_sandbox_helper_ready=lambda _cfg: None))
    b.refresh_os_network_allowlist(SimpleNamespace(setup_mode=False, config={}))

    enabled_calls = []
    monkeypatch.setitem(sys.modules, "democrai.core.infrastructure.sandbox.os.state", SimpleNamespace(is_application_network_allowlist_enabled=lambda _cfg: True, set_application_network_allowlist_active=lambda v: enabled_calls.append(v)))
    monkeypatch.setitem(sys.modules, "democrai.core.infrastructure.sandbox.os.events", SimpleNamespace(register_os_sandbox_event_listeners=lambda: enabled_calls.append("reg"), emit_application_network_allowlist_refresh_event=lambda payload=None: asyncio.sleep(0, result=enabled_calls.append(payload))))
    monkeypatch.setitem(sys.modules, "democrai.core.infrastructure.sandbox.os.helper", SimpleNamespace(ensure_os_sandbox_helper_ready=lambda _cfg: enabled_calls.append("helper")))
    b.refresh_os_network_allowlist(SimpleNamespace(setup_mode=False, config={}))
    assert enabled_calls

    # init_config and setup_storage
    monkeypatch.setattr(pipeline_mod, "get_data_dir", lambda: "/tmp")
    monkeypatch.setattr(pipeline_mod.os.path, "exists", lambda _p: False)
    monkeypatch.setattr(pipeline_mod, "YamlConfigProvider", lambda path: {"path": path})
    ctx_cfg = SimpleNamespace(logger=logger)
    b.init_config(ctx_cfg)
    assert ctx_cfg.setup_mode is True

    def _unexpected_setup_provider(*_a, **_k):
        raise AssertionError("setup storage must not initialize sqlite providers")

    monkeypatch.setattr(pipeline_mod, "PersistenceProviderFactory", SimpleNamespace(get_provider=_unexpected_setup_provider))
    monkeypatch.setattr(pipeline_mod, "MediaProviderFactory", SimpleNamespace(get_provider=lambda *_a, **_k: "media"))
    monkeypatch.setattr(pipeline_mod, "ObservabilityFactory", SimpleNamespace(get_provider=_unexpected_setup_provider))
    monkeypatch.setattr(pipeline_mod, "KGStoreFactory", SimpleNamespace(get_provider=_unexpected_setup_provider))
    monkeypatch.setattr(pipeline_mod, "SQLiteVecVectorProvider", _unexpected_setup_provider)
    monkeypatch.setattr(pipeline_mod, "DataStorageProviderFactory", SimpleNamespace(get_provider=_unexpected_setup_provider))
    monkeypatch.setattr(pipeline_mod, "get_data_dir", lambda: "/tmp")
    ctx_setup = SimpleNamespace(logger=logger)
    b.init_setup_storage(ctx_setup)
    assert ctx_setup.db is None
    assert ctx_setup.media == "media"
    assert ctx_setup.obs_store is None
    assert ctx_setup.kg_store is None
    assert ctx_setup.vector_store is None
    assert ctx_setup.data_store is None
    assert ctx_setup.knowledge_runtime is None

    monkeypatch.setattr(pipeline_mod.bootstrap_pipeline_helpers, "init_knowledge", lambda _ctx: "ok")
    assert b.init_knowledge(SimpleNamespace(setup_mode=True)) is None
    assert b.init_knowledge(SimpleNamespace(setup_mode=False)) == "ok"

    # warmup routing
    monkeypatch.setattr(pipeline_mod, "Router", SimpleNamespace(warmup=lambda: [{"module_name": "m", "error": "x"}]))
    b.warmup_routing(SimpleNamespace(logger=logger), SimpleNamespace(mode="desktop"))
    b.warmup_routing(SimpleNamespace(logger=logger), SimpleNamespace(mode="server"))

    # run migrations + start knowledge runtime
    called2 = []
    monkeypatch.setattr(pipeline_mod, "run_storage_migrations", lambda _ctx: called2.append("storage-mig"))
    monkeypatch.setattr(pipeline_mod, "state_dir", lambda: tmp_path)
    ctx_mig = SimpleNamespace(
        db=SimpleNamespace(run_migrations=lambda: called2.append("db-mig")),
        logger=logger,
    )
    b.run_migrations(ctx_mig)
    assert called2 == ["db-mig", "storage-mig"]

    rt = SimpleNamespace(start=lambda: called2.append("start"))
    b.start_knowledge_runtime(SimpleNamespace(knowledge_runtime=None, setup_mode=False, config=SimpleNamespace(get=lambda *_a, **_k: True), network=SimpleNamespace(_loop=object()), logger=logger))
    b.start_knowledge_runtime(SimpleNamespace(knowledge_runtime=rt, setup_mode=True, config=SimpleNamespace(get=lambda *_a, **_k: True), network=SimpleNamespace(_loop=object()), logger=logger))
    b.start_knowledge_runtime(SimpleNamespace(knowledge_runtime=SimpleNamespace(start=lambda: (_ for _ in ()).throw(RuntimeError("x"))), setup_mode=False, config=SimpleNamespace(get=lambda *_a, **_k: True), network=SimpleNamespace(_loop="L"), logger=logger))
    b.start_knowledge_runtime(SimpleNamespace(knowledge_runtime=rt, setup_mode=False, config=SimpleNamespace(get=lambda *_a, **_k: True), network=SimpleNamespace(_loop="L"), logger=logger))
    assert "start" in called2


def test_refresh_os_network_allowlist_applies_process_restrictions(monkeypatch):
    b = pipeline_mod.RuntimeBootstrapper()
    calls: list[str] = []

    monkeypatch.setitem(
        sys.modules,
        "democrai.core.infrastructure.sandbox.os.current_process",
        SimpleNamespace(
            apply_current_process_os_sandbox=lambda _cfg: calls.append("apply"),
            is_os_sandbox_enabled=lambda _cfg: True,
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "democrai.core.infrastructure.sandbox.process_guard",
        SimpleNamespace(
            process_guard_bypass_context=lambda: __import__("contextlib").nullcontext()
        ),
    )
    monkeypatch.setattr(
        core_relaunch_mod,
        "provider_supports_current_process_os_sandbox",
        lambda: True,
    )
    monkeypatch.setitem(
        sys.modules,
        "democrai.core.infrastructure.sandbox.os.state",
        SimpleNamespace(
            is_application_network_allowlist_enabled=lambda _cfg: False,
            set_application_network_allowlist_active=lambda _v: None,
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "democrai.core.infrastructure.sandbox.os.events",
        SimpleNamespace(
            register_os_sandbox_event_listeners=lambda: None,
            emit_application_network_allowlist_refresh_event=lambda payload=None: asyncio.sleep(0),
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "democrai.core.infrastructure.sandbox.os.helper",
        SimpleNamespace(ensure_os_sandbox_helper_ready=lambda _cfg: None),
    )

    b.refresh_os_network_allowlist(SimpleNamespace(setup_mode=False, config={}))
    assert calls == ["apply"]


def test_refresh_os_network_allowlist_raises_on_required_os_sandbox_failure(monkeypatch):
    b = pipeline_mod.RuntimeBootstrapper()

    monkeypatch.setitem(
        sys.modules,
        "democrai.core.infrastructure.sandbox.os.current_process",
        SimpleNamespace(
            apply_current_process_os_sandbox=lambda _cfg: (_ for _ in ()).throw(RuntimeError("boom")),
            is_os_sandbox_enabled=lambda _cfg: True,
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "democrai.core.infrastructure.sandbox.process_guard",
        SimpleNamespace(
            process_guard_bypass_context=lambda: __import__("contextlib").nullcontext()
        ),
    )
    monkeypatch.setattr(
        core_relaunch_mod,
        "provider_supports_current_process_os_sandbox",
        lambda: True,
    )
    monkeypatch.setitem(
        sys.modules,
        "democrai.core.infrastructure.sandbox.os.state",
        SimpleNamespace(
            is_application_network_allowlist_enabled=lambda _cfg: False,
            set_application_network_allowlist_active=lambda _v: None,
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "democrai.core.infrastructure.sandbox.os.events",
        SimpleNamespace(
            register_os_sandbox_event_listeners=lambda: None,
            emit_application_network_allowlist_refresh_event=lambda payload=None: asyncio.sleep(0),
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "democrai.core.infrastructure.sandbox.os.helper",
        SimpleNamespace(ensure_os_sandbox_helper_ready=lambda _cfg: None),
    )

    with pytest.raises(RuntimeError, match="boom"):
        b.refresh_os_network_allowlist(SimpleNamespace(setup_mode=False, config={}))


def test_refresh_os_network_allowlist_skips_current_process_after_launch_reexec(monkeypatch):
    b = pipeline_mod.RuntimeBootstrapper()

    monkeypatch.setitem(
        sys.modules,
        "democrai.core.infrastructure.sandbox.os.current_process",
        SimpleNamespace(
            apply_current_process_os_sandbox=lambda _cfg: (_ for _ in ()).throw(
                AssertionError("current-process sandbox should be skipped")
            ),
            is_os_sandbox_enabled=lambda _cfg: True,
        ),
    )
    monkeypatch.setattr(
        core_relaunch_mod,
        "provider_supports_current_process_os_sandbox",
        lambda: False,
    )
    monkeypatch.setattr(
        core_relaunch_mod,
        "is_core_os_sandbox_relaunched",
        lambda: True,
    )
    monkeypatch.setitem(
        sys.modules,
        "democrai.core.infrastructure.sandbox.os.state",
        SimpleNamespace(
            is_application_network_allowlist_enabled=lambda _cfg: False,
            set_application_network_allowlist_active=lambda _v: None,
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "democrai.core.infrastructure.sandbox.os.events",
        SimpleNamespace(
            register_os_sandbox_event_listeners=lambda: None,
            emit_application_network_allowlist_refresh_event=lambda payload=None: asyncio.sleep(0),
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "democrai.core.infrastructure.sandbox.os.helper",
        SimpleNamespace(ensure_os_sandbox_helper_ready=lambda _cfg: None),
    )

    b.refresh_os_network_allowlist(SimpleNamespace(setup_mode=False, config={}))


def test_refresh_os_network_allowlist_requires_launch_reexec_for_launch_only(monkeypatch):
    b = pipeline_mod.RuntimeBootstrapper()

    monkeypatch.setitem(
        sys.modules,
        "democrai.core.infrastructure.sandbox.os.current_process",
        SimpleNamespace(
            apply_current_process_os_sandbox=lambda _cfg: None,
            is_os_sandbox_enabled=lambda _cfg: True,
        ),
    )
    monkeypatch.setattr(
        core_relaunch_mod,
        "provider_supports_current_process_os_sandbox",
        lambda: False,
    )
    monkeypatch.setattr(
        core_relaunch_mod,
        "is_core_os_sandbox_relaunched",
        lambda: False,
    )

    with pytest.raises(RuntimeError, match="os_sandbox_core_relaunch_required"):
        b.refresh_os_network_allowlist(SimpleNamespace(setup_mode=False, config={}))


def test_core_os_sandbox_relaunch_without_worker_marker_fails(monkeypatch):
    class _Strategy:
        requires_relaunch = True

    cfg = SimpleNamespace(get=lambda key, default=None: True if key == "sandbox.os.enabled" else default)
    monkeypatch.delenv(core_relaunch_mod.CORE_OS_SANDBOX_REEXEC_ENV, raising=False)
    monkeypatch.setattr(core_relaunch_mod, "get_core_launch_strategy", lambda: _Strategy())

    with pytest.raises(RuntimeError, match="os_sandbox_core_worker_launch_required"):
        core_relaunch_mod.ensure_core_os_sandbox_relaunched(SimpleNamespace(config=cfg))


def test_core_os_sandbox_relaunch_marker_prevents_loop(monkeypatch):
    calls: list[str] = []
    cfg = SimpleNamespace(get=lambda key, default=None: True if key == "sandbox.os.enabled" else default)
    monkeypatch.setenv(core_relaunch_mod.CORE_OS_SANDBOX_REEXEC_ENV, "1")
    monkeypatch.setattr(
        core_relaunch_mod,
        "provider_supports_current_process_os_sandbox",
        lambda: False,
    )
    monkeypatch.setattr(
        core_relaunch_mod,
        "_build_core_launch_policy",
        lambda _cfg: calls.append("build"),
    )

    core_relaunch_mod.ensure_core_os_sandbox_relaunched(SimpleNamespace(config=cfg))
    assert calls == []


def test_core_launch_policy_initializes_helper_before_env(monkeypatch):
    calls: list[str] = []
    token_ready = {"value": False}

    def _ready(_cfg):
        calls.append("ready")
        token_ready["value"] = True

    monkeypatch.setattr(core_relaunch_mod, "_ensure_core_sandbox_helper_ready", _ready)
    monkeypatch.setattr(
        core_relaunch_mod,
        "build_framework_network_allowlist",
        lambda config=None: SimpleNamespace(endpoints=[]),
    )
    monkeypatch.setattr(
        core_relaunch_mod,
        "_start_core_proxy_session",
        lambda _allowlist, config=None: {
            "proxy_url": "http://127.0.0.1:1234",
            "session_id": "session-1",
        },
    )
    monkeypatch.setattr(core_relaunch_mod, "_core_execute_access", lambda: ())
    monkeypatch.setattr(core_relaunch_mod, "_core_relaunch_command", lambda: ["/bin/python", "main.py"])

    from democrai.core.infrastructure.sandbox import process_guard as process_guard_mod
    from democrai.core.infrastructure.sandbox.os import helper as helper_mod

    def _token(_cfg):
        calls.append("env")
        return "token" if token_ready["value"] else ""

    monkeypatch.setattr(helper_mod, "get_os_sandbox_helper_socket_path", lambda _cfg: "/tmp/helper.sock")
    monkeypatch.setattr(helper_mod, "get_os_sandbox_policy_file_path", lambda _cfg: "/tmp/policy.json")
    monkeypatch.setattr(helper_mod, "get_os_sandbox_helper_token", _token)
    monkeypatch.setattr(process_guard_mod, "_runtime_access", lambda: ())
    monkeypatch.setattr(process_guard_mod, "_merge_access_rules", lambda *groups: ())

    policy = core_relaunch_mod._build_core_launch_policy(
        SimpleNamespace(get=lambda _key, default=None: default)
    )

    assert calls[:2] == ["ready", "env"]
    assert policy.env[helper_mod.OS_SANDBOX_HELPER_SOCKET_ENV] == "/tmp/helper.sock"
    assert policy.env[helper_mod.OS_SANDBOX_HELPER_TOKEN_ENV] == "token"
    assert policy.env[core_relaunch_mod.CORE_OS_SANDBOX_REEXEC_ENV] == "1"
    assert policy.env[core_relaunch_mod.CORE_OS_SANDBOX_PROXY_SESSION_ENV] == "session-1"


def test_core_media_storage_access_uses_launch_config():
    media_path = "/tmp/democrai-media"

    cfg = SimpleNamespace(
        get=lambda key, default=None: {
            "storage.media.type": "local",
            "storage.media.path": media_path,
        }.get(key, default)
    )

    rules = core_relaunch_mod._core_media_storage_access(cfg)
    operations = {
        rule.resource.operation.value
        for rule in rules
        if rule.resource.normalized_target == media_path
    }

    assert operations == {"read", "create", "modify", "delete"}
