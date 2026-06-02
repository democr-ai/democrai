from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace

import democrai.core.runtime.bootstrap.bootstrap_pipeline as mod
import pytest


class _Cfg:
    def __init__(self, data):
        self._data = data

    def get(self, key, default=None):
        return self._data.get(key, default)


class _Logger:
    def __init__(self):
        self.info_msgs = []
        self.warn_msgs = []
        self.error_msgs = []
        self.debug_msgs = []

    def info(self, *args, **kwargs):
        self.info_msgs.append(args)

    def warning(self, *args, **kwargs):
        self.warn_msgs.append(args)

    def error(self, *args, **kwargs):
        self.error_msgs.append(args)

    def debug(self, *args, **kwargs):
        self.debug_msgs.append(args)


def test_init_storage_non_setup(monkeypatch):
    called = []
    b = mod.RuntimeBootstrapper()
    monkeypatch.setattr(b, "init_knowledge", lambda ctx: called.append("knowledge"))
    monkeypatch.setattr(mod, "install_sqlalchemy_audit_hooks", lambda: called.append("audit"))

    monkeypatch.setattr(mod, "PersistenceProviderFactory", SimpleNamespace(get_provider=lambda *a, **k: "db"))
    monkeypatch.setattr(mod, "MediaProviderFactory", SimpleNamespace(get_provider=lambda *a, **k: "media"))

    class _ObsStore:
        def flush_export_outbox(self):
            return None

        def apply_retention(self):
            return None

    monkeypatch.setattr(mod, "ObservabilityFactory", SimpleNamespace(get_provider=lambda *a, **k: _ObsStore()))
    monkeypatch.setattr(mod, "KGStoreFactory", SimpleNamespace(get_provider=lambda *a, **k: "kg"))
    monkeypatch.setattr(mod, "VectorStoreFactory", SimpleNamespace(get_provider=lambda *a, **k: "vec"))
    monkeypatch.setattr(mod, "DataStorageProviderFactory", SimpleNamespace(get_provider=lambda *a, **k: "data"))

    class _ObsMaint:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def start(self):
            called.append("obs-start")

    monkeypatch.setattr(mod, "ObservabilityMaintenanceService", _ObsMaint)

    cfg = _Cfg(
        {
            "database.type": "sqlite",
            "database.url": "sqlite:///db",
            "database.data_type": "sqlite",
            "database.data_url": "sqlite:///data",
            "storage.media.type": "local",
            "storage.observability.type": "sqlite",
            "storage.kg.type": "ladybug",
            "storage.vector.type": "sqlite-vec",
        }
    )
    ctx = SimpleNamespace(setup_mode=False, config=cfg, logger=_Logger())

    b.init_storage(ctx)
    assert ctx.db == "db"
    assert ctx.media == "media"
    assert ctx.kg_store == "kg"
    assert ctx.vector_store == "vec"
    assert ctx.data_store == "data"
    assert "audit" in called
    assert "obs-start" in called
    assert "knowledge" in called

    # no maintenance service when store lacks methods
    called.clear()
    monkeypatch.setattr(mod, "ObservabilityFactory", SimpleNamespace(get_provider=lambda *a, **k: object()))
    ctx2 = SimpleNamespace(setup_mode=False, config=cfg, logger=_Logger())
    b.init_storage(ctx2)
    assert ctx2.obs_maintenance_service is None


def test_init_network_server_desktop_redis_and_callbacks(monkeypatch):
    class _WsBus:
        def __init__(self):
            self.broadcasts = []

        def broadcast(self, msg):
            self.broadcasts.append(msg)

    class _IpcBus:
        def __init__(self, name):
            self.name = name
            self._sockets = {"client-1": object()}
            self.sent = []
            self.broadcasts = []

        def send(self, client_id, msg):
            self.sent.append((client_id, msg))

        def broadcast(self, msg):
            self.broadcasts.append(msg)

    class _RedisBus:
        def __init__(self, node_id, redis_url):
            self.node_id = node_id
            self.redis_url = redis_url
            self.local_send = None
            self.local_broadcast = None

    monkeypatch.setitem(sys.modules, "democrai.core.infrastructure.network.providers.bus.ws", SimpleNamespace(WsBusProvider=_WsBus))
    monkeypatch.setitem(sys.modules, "democrai.core.infrastructure.network.providers.bus.ipc", SimpleNamespace(IpcBusProvider=_IpcBus))
    monkeypatch.setitem(sys.modules, "democrai.core.infrastructure.network.providers.bus.redis", SimpleNamespace(RedisBusProvider=_RedisBus))

    monkeypatch.setattr(mod, "StreamProviderFactory", SimpleNamespace(get_provider=lambda *a, **k: "streams"))

    class _Network:
        def __init__(self, buses, streams):
            self.buses = buses
            self.streams = streams
            self.ipc = None

    monkeypatch.setattr(mod, "Network", _Network)

    logger = _Logger()
    b = mod.RuntimeBootstrapper()
    cfg = _Cfg(
        {
            "network.node_id": "node",
            "network.redis.enabled": True,
            "network.redis.url": "redis://r",
            "network.stream.type": "redis",
        }
    )
    ctx = SimpleNamespace(config=cfg, logger=logger)

    b.init_network(ctx, SimpleNamespace(mode="desktop", http=True))
    assert ctx.network.ipc is not None
    redis_bus = next(bus for bus in ctx.network.buses if isinstance(bus, _RedisBus))
    redis_bus.local_send("client-1", {"x": 1})
    redis_bus.local_send("missing", {"x": 1})
    redis_bus.local_broadcast({"b": 1})
    assert logger.warn_msgs

    # server mode, no ipc
    ctx2 = SimpleNamespace(config=_Cfg({"network.redis.enabled": False, "network.stream.type": "memory"}), logger=_Logger())
    b.init_network(ctx2, SimpleNamespace(mode="server", http=False))
    assert ctx2.network.ipc is None


def test_start_install_runtimes(monkeypatch):
    b = mod.RuntimeBootstrapper()

    # engine runtime: setup mode short-circuit
    b.start_engine_install_runtime(SimpleNamespace(setup_mode=True))

    events = []
    async_calls = []

    async def _sync_active():
        events.append("sync-eng")

    monkeypatch.setitem(
        sys.modules,
        "democrai.core.application.ai.engine.install_events",
        SimpleNamespace(
            start_engine_install_consumer=lambda: events.append("eng-cons"),
            start_engine_install_reconcile=lambda: events.append("eng-rec"),
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "democrai.core.application.ai.engine.runtime",
        SimpleNamespace(get_engine_runtime=lambda: SimpleNamespace(sync_active_engines=lambda: _sync_active())),
    )

    def _run_coroutine_threadsafe(coro, loop):
        async_calls.append((coro, loop))
        coro.close()
        return SimpleNamespace()

    monkeypatch.setattr(asyncio, "run_coroutine_threadsafe", _run_coroutine_threadsafe)

    ctx = SimpleNamespace(setup_mode=False, network=SimpleNamespace(_loop="L"))
    b.start_engine_install_runtime(ctx)
    assert "eng-cons" in events and "eng-rec" in events
    assert async_calls and async_calls[0][1] == "L"

    # extractor runtime
    events2 = []
    async_calls2 = []

    async def _sync_ext():
        events2.append("sync-ext")

    monkeypatch.setitem(
        sys.modules,
        "democrai.core.application.knowledge.extractor.install_events",
        SimpleNamespace(
            start_extractor_install_consumer=lambda: events2.append("ext-cons"),
            start_extractor_install_reconcile=lambda: events2.append("ext-rec"),
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "democrai.core.application.knowledge.extractor.runtime",
        SimpleNamespace(get_extractor_runtime=lambda: SimpleNamespace(sync_active_extractors=lambda: _sync_ext())),
    )

    monkeypatch.setattr(asyncio, "run_coroutine_threadsafe", lambda coro, loop: (async_calls2.append((coro, loop)), coro.close(), SimpleNamespace())[2])

    b.start_extractor_install_runtime(SimpleNamespace(setup_mode=False, network=SimpleNamespace(_loop="L2")))
    assert "ext-cons" in events2 and "ext-rec" in events2
    assert async_calls2 and async_calls2[0][1] == "L2"


def test_bootstrap_additional_paths(monkeypatch):
    b = mod.RuntimeBootstrapper()
    logger = _Logger()

    # init_storage setup-mode branch
    setup_calls = []
    monkeypatch.setattr(b, "init_setup_storage", lambda _ctx: setup_calls.append("setup"))
    b.init_storage(SimpleNamespace(setup_mode=True))
    assert setup_calls == ["setup"]

    def _unexpected_setup_provider(*_a, **_k):
        raise AssertionError("setup storage must not initialize sqlite providers")

    monkeypatch.setattr(mod, "PersistenceProviderFactory", SimpleNamespace(get_provider=_unexpected_setup_provider))
    monkeypatch.setattr(mod, "ObservabilityFactory", SimpleNamespace(get_provider=_unexpected_setup_provider))
    monkeypatch.setattr(mod, "KGStoreFactory", SimpleNamespace(get_provider=_unexpected_setup_provider))
    monkeypatch.setattr(mod, "SQLiteVecVectorProvider", _unexpected_setup_provider)
    monkeypatch.setattr(mod, "DataStorageProviderFactory", SimpleNamespace(get_provider=_unexpected_setup_provider))
    monkeypatch.setattr(mod, "MediaProviderFactory", SimpleNamespace(get_provider=lambda *_a, **_k: "media"))
    setup_ctx = SimpleNamespace(setup_mode=True, logger=logger)
    mod.RuntimeBootstrapper().init_storage(setup_ctx)
    assert setup_ctx.db is None
    assert setup_ctx.media == "media"
    assert setup_ctx.obs_store is None
    assert setup_ctx.kg_store is None
    assert setup_ctx.vector_store is None
    assert setup_ctx.data_store is None

    # warmup success branch
    monkeypatch.setattr(mod, "Router", SimpleNamespace(warmup=lambda: []))
    b.warmup_routing(SimpleNamespace(logger=logger), SimpleNamespace(mode="desktop"))
    assert logger.info_msgs

    # init_modules passthrough
    monkeypatch.setattr(mod.bootstrap_pipeline_helpers, "init_modules", lambda _ctx, _args: "ok-init-mods")
    out = b.init_modules(SimpleNamespace(config=object()), SimpleNamespace())
    assert out == "ok-init-mods"

    # bootstrap setup mode + server http init branch + network stop error logging branch
    order = []
    ctx = SimpleNamespace(
        logger=SimpleNamespace(
            info=lambda *a, **k: order.append(("info", a)),
            warning=lambda *a, **k: order.append(("warn", a)),
            error=lambda *a, **k: order.append(("err", a)),
            debug=lambda *a, **k: order.append(("dbg", a)),
        ),
        setup_mode=True,
    )
    monkeypatch.setattr(mod, "app_ctx", lambda: ctx)
    b.init_config = lambda _ctx: None
    b.refresh_os_network_allowlist = lambda _ctx: None
    b.init_storage = lambda _ctx: None
    b.sync_engine_registry = lambda _ctx: None

    def _init_network(_ctx, _args):
        def _init_http_ws(*a, **k):
            order.append(("http", a, k))
            raise RuntimeError("http-fail")

        _ctx.network = SimpleNamespace(
            start=lambda: order.append(("network-start", ())),
            stop=lambda: (_ for _ in ()).throw(RuntimeError("stop-fail")),
            core=SimpleNamespace(session_service=SimpleNamespace(start_cleanup_loop=lambda: None)),
            init_http_ws=_init_http_ws,
            _loop=None,
        )

    b.init_network = _init_network
    b.init_modules = lambda _ctx, _args: setattr(_ctx, "modules", SimpleNamespace(schedule_startup=lambda _loop: None))
    b.warmup_routing = lambda _ctx, _args: None
    b.run_migrations = lambda _ctx: order.append(("migrations", ()))
    b.sync_extractor_registry = lambda _ctx: order.append(("extractor-sync", ()))
    b.start_engine_install_runtime = lambda _ctx: order.append(("engine-runtime", ()))
    b.start_extractor_install_runtime = lambda _ctx: None
    b.start_knowledge_runtime = lambda _ctx: None

    with pytest.raises(RuntimeError):
        b.bootstrap(SimpleNamespace(mode="server", http=False, host="0.0.0.0", port=9999, listen_fd=7))
    assert any(item[0] == "http" for item in order)
    assert any(item[0] == "err" for item in order)


def test_start_install_runtime_sync_coroutines_execute(monkeypatch):
    b = mod.RuntimeBootstrapper()
    events = []

    class _EngRuntime:
        async def sync_active_engines(self):
            events.append("eng-sync")

    class _ExtRuntime:
        async def sync_active_extractors(self):
            events.append("ext-sync")

    monkeypatch.setitem(
        sys.modules,
        "democrai.core.application.ai.engine.install_events",
        SimpleNamespace(
            start_engine_install_consumer=lambda: None,
            start_engine_install_reconcile=lambda: None,
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "democrai.core.application.ai.engine.orchestrator.client",
        SimpleNamespace(EngineOrchestratorClient=lambda: SimpleNamespace(sync_active_engines=lambda: events.append("eng-sync"))),
    )
    monkeypatch.setitem(
        sys.modules,
        "democrai.core.application.ai.engine.runtime",
        SimpleNamespace(get_engine_runtime=lambda: _EngRuntime()),
    )
    monkeypatch.setitem(
        sys.modules,
        "democrai.core.application.knowledge.extractor.install_events",
        SimpleNamespace(
            start_extractor_install_consumer=lambda: None,
            start_extractor_install_reconcile=lambda: None,
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "democrai.core.application.knowledge.extractor.runtime",
        SimpleNamespace(get_extractor_runtime=lambda: _ExtRuntime()),
    )

    def _run_coroutine_threadsafe(coro, _loop):
        asyncio.run(coro)
        return SimpleNamespace()

    monkeypatch.setattr(asyncio, "run_coroutine_threadsafe", _run_coroutine_threadsafe)

    b.start_engine_install_runtime(SimpleNamespace(setup_mode=False, network=SimpleNamespace(_loop="L")))
    b.start_extractor_install_runtime(SimpleNamespace(setup_mode=False, network=SimpleNamespace(_loop="L")))
    assert "eng-sync" in events
    assert "ext-sync" in events
