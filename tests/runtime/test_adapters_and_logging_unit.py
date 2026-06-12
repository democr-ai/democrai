from __future__ import annotations

import json
import logging
from types import SimpleNamespace

import democrai.core.infrastructure.database as db_mod
import democrai.core.infrastructure.database.migrations_handler as db_migrations_mod
import democrai.core.infrastructure.observability.logger.manager as logger_manager_mod
import democrai.core.infrastructure.observability.logger.providers.cloud as cloud_log_mod
import democrai.core.infrastructure.observability.logger.providers.local as local_log_mod
import democrai.core.infrastructure.observability.logging as logging_adapter_mod
import pytest


class _Logger:
    def __init__(self):
        self.infos = []
        self.errors = []
        self.debugs = []

    def info(self, message, *args, **kwargs):
        self.infos.append(message)

    def error(self, message, *args, **kwargs):
        self.errors.append(message)

    def debug(self, message, *args, **kwargs):
        self.debugs.append(message)


class _DBSession:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class _Handler(logging.Handler):
    def __init__(self, *args, **kwargs):
        super().__init__()
        self.closed_flag = False
        self.records = []

    def emit(self, record):
        self.records.append(record)

    def close(self):
        self.closed_flag = True
        super().close()


@pytest.mark.posix_only
def test_database_helpers_cover_config_lazy_and_proxy_paths(monkeypatch):
    ctx = SimpleNamespace(
        config=SimpleNamespace(
            get=lambda key: {"database.url": "sqlite:///ctx.db"}.get(key)
        ),
        db=None,
    )
    monkeypatch.setattr(db_mod, "app_ctx", lambda: ctx)
    db_mod._db_url = None
    assert db_mod.get_database_url() == "sqlite:///ctx.db"

    created = {}
    db_mod._db_url = None
    db_mod._default_engine = None
    db_mod._default_SessionLocal = None
    monkeypatch.setattr(
        db_mod, "app_ctx", lambda: SimpleNamespace(config=None, db=None)
    )
    monkeypatch.setattr(db_mod, "get_data_dir", lambda: "/tmp/demo")
    monkeypatch.setattr(
        db_mod,
        "create_engine",
        lambda url, connect_args=None: created.setdefault(
            "engine", (url, connect_args)
        ),
    )
    monkeypatch.setattr(db_mod, "sessionmaker", lambda **kwargs: (lambda: _DBSession()))
    monkeypatch.setattr(db_mod, "scoped_session", lambda factory: factory)
    monkeypatch.setattr(db_mod, "install_sqlite_engine_pragmas", lambda _engine: None)

    assert db_mod.get_database_url() == "sqlite:////tmp/demo/democrai.db"
    assert isinstance(db_mod._get_lazy_session()(), _DBSession)
    assert created["engine"] == (
        "sqlite:////tmp/demo/democrai.db",
        {"check_same_thread": False, "timeout": 5.0},
    )

    explicit_db = _DBSession()
    monkeypatch.setattr(
        db_mod,
        "app_ctx",
        lambda: SimpleNamespace(
            config=None, db=SimpleNamespace(get_session=lambda: explicit_db)
        ),
    )
    gen = db_mod.get_db()
    assert next(gen) is explicit_db
    try:
        next(gen)
    except StopIteration:
        pass
    assert explicit_db.closed is True

    fallback_db = _DBSession()
    monkeypatch.setattr(
        db_mod, "app_ctx", lambda: SimpleNamespace(config=None, db=None)
    )
    monkeypatch.setattr(db_mod, "_get_lazy_session", lambda: (lambda: fallback_db))
    gen = db_mod.get_db()
    assert next(gen) is fallback_db
    try:
        next(gen)
    except StopIteration:
        pass
    assert fallback_db.closed is True
    db_mod._db_url = None
    db_mod._default_engine = None
    db_mod._default_SessionLocal = None

    proxied = _DBSession()
    monkeypatch.setattr(
        db_mod,
        "app_ctx",
        lambda: SimpleNamespace(
            config=None, db=SimpleNamespace(get_session=lambda: proxied)
        ),
    )
    assert db_mod.SessionLocal() is proxied


@pytest.mark.posix_only
def test_database_migrations_handler_logs_success_and_errors(monkeypatch):
    logger = _Logger()
    monkeypatch.setattr(
        db_migrations_mod, "app_ctx", lambda: SimpleNamespace(logger=logger)
    )
    monkeypatch.setattr(db_migrations_mod, "get_base_dir", lambda: "/base")

    configs = []

    class _Config:
        def __init__(self, path):
            self.path = path
            self.options = {}
            self.attributes = {}
            configs.append(self)

        def set_main_option(self, key, value):
            self.options[key] = value

    monkeypatch.setattr(db_migrations_mod, "Config", _Config)
    monkeypatch.setattr(
        "democrai.core.infrastructure.database.get_database_url", lambda: "sqlite:///main.db"
    )
    monkeypatch.setattr(
        "democrai.core.infrastructure.database.models.Base", SimpleNamespace(metadata="META")
    )
    calls = []
    monkeypatch.setattr(
        db_migrations_mod.command,
        "upgrade",
        lambda cfg, target: calls.append((cfg, target)),
    )

    db_migrations_mod.run_migrations()
    cfg = configs[0]
    assert cfg.path == "/base/core/infrastructure/database/alembic.ini"
    assert (
        cfg.options["script_location"]
        == "/base/core/infrastructure/database/migrations"
    )
    assert cfg.options["sqlalchemy.url"] == "sqlite:///main.db"
    assert cfg.attributes["target_metadata"] == "META"
    assert calls == [(cfg, "head")]

    monkeypatch.setattr(
        db_migrations_mod.command,
        "upgrade",
        lambda cfg, target: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    db_migrations_mod.run_migrations()
    assert any("Error during migrations" in msg for msg in logger.errors)


def test_logger_manager_and_providers_cover_core_paths(monkeypatch, tmp_path):
    monkeypatch.setattr(logger_manager_mod, "dictConfig", lambda cfg: cfg)
    monkeypatch.setattr(local_log_mod, "TimedRotatingFileHandler", _Handler)
    monkeypatch.setattr(
        local_log_mod, "os", SimpleNamespace(getenv=lambda name: "warning")
    )
    monkeypatch.setattr(
        logger_manager_mod, "os", SimpleNamespace(getenv=lambda name: "error")
    )

    provider = local_log_mod.LocalFileLogProvider(log_dir=tmp_path)
    handlers = provider.get_handlers("Main.UI")
    assert len(handlers) == 1
    record = logging.LogRecord("demo", logging.INFO, __file__, 1, "msg", (), None)
    assert handlers[0].filters[0].filter(record) is True
    assert record.clientip == "-"
    assert record.user == "-"
    assert record.uid == "-"
    assert local_log_mod.normalize_logger_name("Main.UI!!") == "main_ui__"
    assert logger_manager_mod.normalize_logger_name("Main.UI!!") == "main_ui__"
    assert provider.level == logging.WARNING
    cloud_handlers = cloud_log_mod.CloudLogProvider(
        "https://logs.example.test/ingest?node=1",
        "key",
    ).get_handlers("demo")
    assert len(cloud_handlers) == 1
    assert cloud_handlers[0].host == "logs.example.test"
    assert cloud_handlers[0].url == "/ingest?node=1"
    assert cloud_handlers[0].method == "POST"
    assert cloud_handlers[0].secure is True
    sent = {}

    class _Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    def _urlopen(request, timeout):
        sent["url"] = request.full_url
        sent["method"] = request.get_method()
        sent["data"] = json.loads(request.data.decode("utf-8"))
        sent["content_type"] = request.headers["Content-type"]
        sent["timeout"] = timeout
        return _Response()

    monkeypatch.setattr(cloud_log_mod.urllib.request, "urlopen", _urlopen)
    cloud_record = logging.LogRecord(
        "demo",
        logging.WARNING,
        __file__,
        42,
        "cloud %s",
        ("msg",),
        None,
    )
    cloud_record.user = "fabio"
    cloud_handlers[0].emit(cloud_record)
    assert sent["url"] == "https://logs.example.test/ingest?node=1"
    assert sent["method"] == "POST"
    assert sent["data"]["message"] == "cloud msg"
    assert sent["data"]["level"] == "WARNING"
    assert sent["data"]["user"] == "fabio"
    assert sent["content_type"] == "application/json"
    assert sent["timeout"] == 5.0
    assert cloud_log_mod.CloudLogProvider("https://logs").endpoint == "https://logs"

    handler = _Handler()

    class _Provider:
        def get_handlers(self, name):
            return [handler]

    manager = logger_manager_mod.LoggerManager(
        log_dir=tmp_path,
        providers=[_Provider()],
        default_level=logging.DEBUG,
    )
    adapter = manager.get("custom", uid="u1", clientip="127.0.0.1", user="fabio")
    adapter.info("hello")
    manager.info("i", name="custom")
    manager.warning("w", name="custom")
    manager.error("e", name="custom")
    manager.debug("d", name="custom")
    manager.critical("c", name="custom")
    assert handler.records
    assert any(
        record.pathname.endswith("test_adapters_and_logging_unit.py")
        for record in handler.records
    )
    with_exc = next(record for record in handler.records if record.getMessage() == "e")
    assert with_exc.funcName == "test_logger_manager_and_providers_cover_core_paths"

    try:
        raise RuntimeError("boom")
    except RuntimeError:
        manager.error("error-with-trace", name="custom")
        manager.exception("exception-with-trace", name="custom")

    traced_error = next(
        record
        for record in handler.records
        if record.getMessage() == "error-with-trace"
    )
    traced_exception = next(
        record
        for record in handler.records
        if record.getMessage() == "exception-with-trace"
    )
    assert traced_error.exc_info is not None
    assert traced_exception.exc_info is not None

    same = manager._get_or_create_logger("custom")
    assert same is manager._get_or_create_logger("custom")
    manager.destroy("custom")
    assert handler.closed_flag is True
    manager.destroy("missing")
    manager.destroy("main")

    adapter_logger = logging_adapter_mod.LoggerAdapter(
        SimpleNamespace(
            info=lambda message, channel: handler.records.append((message, channel))
        )
    )
    adapter_logger.info("msg", channel="core")
    logging_adapter_mod.LoggerAdapter().info("noop")

    assert (
        logger_manager_mod._resolve_log_level("DEMOCRAI_LOG_LEVEL", logging.INFO)
        == logging.ERROR
    )
    monkeypatch.setattr(
        logger_manager_mod, "os", SimpleNamespace(getenv=lambda name: None)
    )
    monkeypatch.setattr(logger_manager_mod, "sys", SimpleNamespace(frozen=True))
    assert logger_manager_mod._default_log_level() == logging.INFO
    monkeypatch.setattr(local_log_mod, "sys", SimpleNamespace())
    assert local_log_mod._default_log_level() == logging.DEBUG


def test_logger_manager_default_provider_and_dynamic_level(monkeypatch, tmp_path):
    monkeypatch.setattr(logger_manager_mod, "dictConfig", lambda cfg: cfg)
    monkeypatch.setattr(
        logger_manager_mod,
        "LocalFileLogProvider",
        lambda log_dir: SimpleNamespace(get_handlers=lambda _name: []),
    )
    monkeypatch.setattr(
        logger_manager_mod, "os", SimpleNamespace(getenv=lambda _name: "warning")
    )
    manager = logger_manager_mod.LoggerManager(
        log_dir=tmp_path, providers=None, default_level=None
    )
    assert manager.default_level == logging.WARNING
    assert manager.get().logger.name == "main"

    http_calls = []
    monkeypatch.setattr(
        logger_manager_mod,
        "CloudLogProvider",
        lambda url, method: http_calls.append((url, method))
        or SimpleNamespace(get_handlers=lambda _name: []),
    )
    cfg = SimpleNamespace(
        get=lambda key, default=None: {
            "logging.provider": "http",
            "logging.url": "https://logs.example.test/ingest",
            "logging.method": "post",
        }.get(key, default)
    )
    logger_manager_mod.LoggerManager(log_dir=tmp_path, config=cfg)
    assert http_calls == [("https://logs.example.test/ingest", "POST")]


def test_logging_remaining_branches(monkeypatch):
    record = logging.LogRecord("demo", logging.INFO, __file__, 1, "msg", (), None)
    assert logger_manager_mod.EnsureExtrasFilter().filter(record) is True
    assert record.clientip == "-"
    assert record.user == "-"
    assert record.uid == "-"

    monkeypatch.setattr(local_log_mod, "os", SimpleNamespace(getenv=lambda _name: None))
    assert local_log_mod._resolve_log_level("ANY", logging.INFO) == logging.INFO
    monkeypatch.setattr(local_log_mod, "sys", SimpleNamespace(frozen=True))
    assert local_log_mod._default_log_level() == logging.INFO

    monkeypatch.setattr(
        logger_manager_mod, "os", SimpleNamespace(getenv=lambda _name: None)
    )
    assert logger_manager_mod._resolve_log_level("ANY", logging.DEBUG) == logging.DEBUG

    # keep existing extras -> "hasattr" false branch in filter loop
    record2 = logging.LogRecord("demo", logging.INFO, __file__, 1, "msg", (), None)
    record2.clientip = "1.1.1.1"
    record2.user = "u"
    record2.uid = "id"
    assert local_log_mod.EnsureExtrasFilter().filter(record2) is True
    assert logger_manager_mod.EnsureExtrasFilter().filter(record2) is True

    monkeypatch.setattr(logger_manager_mod, "dictConfig", lambda _cfg: None)

    h1 = _Handler()
    h2 = _Handler()

    class _DupProvider:
        def get_handlers(self, _name):
            return [h1, h2]

    manager = logger_manager_mod.LoggerManager(
        providers=[_DupProvider()],
        default_level=logging.INFO,
    )
    logger = manager._get_or_create_logger("dup-case")
    same_type_handlers = [h for h in logger.handlers if isinstance(h, _Handler)]
    assert len(same_type_handlers) == 1
