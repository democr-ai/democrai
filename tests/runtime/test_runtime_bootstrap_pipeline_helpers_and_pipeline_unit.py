from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace

import pytest

import democrai.core.infrastructure.sandbox.os.bootstrap as os_sandbox_bootstrap_mod
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
    assert order[:5] == ["config", "logging", "allow", "storage", "engine-reg"]
    assert "http" in order

    # failure path after network start
    stop_calls = []
    ctx2 = SimpleNamespace(logger=logger, setup_mode=False, network=SimpleNamespace(stop=lambda: stop_calls.append("stopped")))
    monkeypatch.setattr(pipeline_mod, "app_ctx", lambda: ctx2)
    b2 = pipeline_mod.RuntimeBootstrapper()
    b2.init_config = lambda _ctx: None
    b2.configure_logging = lambda _ctx: None
    b2.refresh_os_network_allowlist = lambda _ctx: None
    b2.init_storage = lambda _ctx: None
    b2.sync_engine_registry = lambda _ctx: None
    b2.init_network = lambda _ctx, _args: None
    b2.init_modules = lambda _ctx, _args: None
    b2.sync_environment_definitions = lambda _ctx: None
    b2.warmup_routing = lambda _ctx, _args: None
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


def test_pipeline_misc_methods(monkeypatch):
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
