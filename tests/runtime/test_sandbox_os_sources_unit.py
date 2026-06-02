from __future__ import annotations

import importlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import OperationalError

from democrai.core.infrastructure.sandbox.os.models import NetworkEndpoint


def _write_manifest(root: Path, folder: str, payload: dict) -> None:
    path = root / folder
    path.mkdir(parents=True, exist_ok=True)
    (path / "manifest.json").write_text(json.dumps(payload), encoding="utf-8")


def test_sources_small_helpers(tmp_path: Path):
    mod = importlib.import_module("democrai.core.infrastructure.sandbox.os.sources")

    valid = tmp_path / "ok.json"
    valid.write_text(json.dumps({"a": 1}), encoding="utf-8")
    assert mod._load_json_file(valid) == {"a": 1}

    invalid = tmp_path / "invalid.json"
    invalid.write_text("{bad", encoding="utf-8")
    assert mod._load_json_file(invalid) is None

    not_dict = tmp_path / "arr.json"
    not_dict.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    assert mod._load_json_file(not_dict) is None

    assert list(mod._iter_manifest_payloads(tmp_path / "missing")) == []
    assert list(mod._iter_manifest_payloads(valid)) == []

    modules_root = tmp_path / "mods"
    modules_root.mkdir()
    (modules_root / "plain.txt").write_text("x", encoding="utf-8")
    _write_manifest(
        modules_root,
        "a_mod",
        {
            "name": "A",
            "access": [
                {
                    "resource_type": "network",
                    "operation": "receive",
                    "target": "https://api.local:443",
                },
            ],
        },
    )
    _write_manifest(modules_root, "b_mod", {"name": "B", "access": []})
    (modules_root / "c_mod").mkdir()
    (modules_root / "d_mod").mkdir()
    (modules_root / "d_mod" / "manifest.json").write_text("{bad", encoding="utf-8")
    items = list(mod._iter_manifest_payloads(modules_root))
    assert len(items) == 2

    assert mod._config_get(SimpleNamespace(get=lambda k, d=None: "x"), "k", "d") == "x"
    assert mod._config_get(SimpleNamespace(), "k", "d") == "d"

    endpoints = mod._targets_from_iterable(
        ["https://api.local:443/path", "", "not-a-target", "https://api.local:443/path"],
        source="s",
        purpose="p",
    )
    assert len(endpoints) == 1 and endpoints[0].host == "api.local"

    assert mod._host_port_endpoint("", 443, source="s", purpose="p") is None
    endpoint = mod._host_port_endpoint("api.local", 443, source="s", purpose="p")
    assert endpoint == NetworkEndpoint(
        host="api.local",
        port=443,
        protocol="tcp",
        source="s",
        purpose="p",
    )

    cfg = SimpleNamespace(get=lambda key, default=None: {"good": "https://db.local:5432"}.get(key, default))
    assert mod._config_url_endpoint(cfg, key="missing", source="s", purpose="p") is None
    endpoint = mod._config_url_endpoint(cfg, key="good", source="s", purpose="p")
    assert endpoint is not None and endpoint.host == "db.local"


def test_collect_config_endpoints_and_observed(monkeypatch):
    mod = importlib.import_module("democrai.core.infrastructure.sandbox.os.sources")

    config_values = {
        "database.type": "postgres",
        "database.url": "postgresql://db.local:5432/app",
        "database.data_type": "supabase",
        "database.data_url": "https://data.local:443",
        "storage.media.type": "s3",
        "storage.media.endpoint_url": "https://media.local:9000",
        "storage.kg.type": "neo4j",
        "storage.kg.uri": "neo4j://kg.local:7687",
        "storage.vector.type": "milvus",
        "storage.vector.host": "vector.local",
        "storage.vector.port": 19530,
        "storage.vector.url": "https://vector.local:443",
        "storage.observability.type": "clickhouse",
        "storage.observability.url": "https://obs.local:8443",
        "storage.observability.exporters.otlp.enabled": True,
        "storage.observability.exporters.otlp.endpoint": "https://otlp.local:4317",
        "logging.provider": "http",
        "logging.url": "https://logs.local:9443/ingest",
        "network.redis.enabled": True,
        "network.redis.url": "redis://cache.local:6379",
        "session.redis.url": "redis://session.local:6379",
        "session.ui_state.provider": "redis",
        "session.ui_state.url": "redis://ui.local:6379",
        "session.cache.provider": "redis",
    }
    config = SimpleNamespace(get=lambda key, default=None: config_values.get(key, default))
    endpoints = mod.collect_config_endpoints(config)
    hosts = {e.host for e in endpoints}
    assert "db.local" in hosts
    assert "data.local" in hosts
    assert "media.local" in hosts
    assert "kg.local" in hosts
    assert "vector.local" in hosts
    assert "obs.local" in hosts
    assert "otlp.local" in hosts
    assert "logs.local" in hosts
    assert "cache.local" in hosts
    assert "session.local" in hosts
    assert "ui.local" in hosts

    assert mod.collect_config_endpoints(None) == []

    monkeypatch.setattr(
        mod,
        "collect_observed_runtime_endpoints",
        lambda _cfg=None: [
            NetworkEndpoint(host="api.local", port=443, protocol="tcp"),
            NetworkEndpoint(host="api.local", port=443, protocol="tcp"),
        ],
    )
    observed = mod.collect_observed_endpoints(config=None)
    assert len(observed) == 1 and observed[0].host == "api.local"


def test_collect_module_engine_extractor_endpoints(tmp_path: Path, monkeypatch):
    mod = importlib.import_module("democrai.core.infrastructure.sandbox.os.sources")

    builtin = tmp_path / "builtin_mods"
    user = tmp_path / "user_mods"
    base = tmp_path / "base"
    builtin.mkdir()
    user.mkdir()
    (base / "engines").mkdir(parents=True)
    (base / "extractors").mkdir(parents=True)

    _write_manifest(
        builtin,
        "m1",
        {
            "name": "ModA",
            "access": [
                {
                    "resource_type": "network",
                    "operation": "receive",
                    "target": "https://a.local:443",
                },
                {
                    "resource_type": "network",
                    "operation": "receive",
                    "target": "https://a.local:443",
                },
            ],
        },
    )
    _write_manifest(
        user,
        "m2",
        {
            "name": "moda",
            "access": [
                {
                    "resource_type": "network",
                    "operation": "receive",
                    "target": "https://b.local:443",
                },
            ],
        },
    )
    _write_manifest(user, "m3", {"name": "ModB", "access": []})

    _write_manifest(
        base / "engines",
        "e1",
            {
                "id": "EngineA",
                "install": {
                    "access": [
                        {
                            "resource_type": "network",
                            "operation": "receive",
                            "target": "https://eng-install.local:443",
                        },
                    ],
                },
                "runtime": {
                    "access": [
                        {
                            "resource_type": "network",
                            "operation": "receive",
                            "target": "https://eng-runtime.local:443",
                        },
                    ],
                },
            },
        )
    _write_manifest(
        base / "engines",
        "e2",
        {
            "id": "",
            "install": {
                "access": [
                    {
                        "resource_type": "network",
                        "operation": "receive",
                        "target": "https://x.local:443",
                    },
                ],
            },
        },
    )

    _write_manifest(
        base / "extractors",
        "x1",
            {
                "id": "ExtractorA",
                "install": {
                    "access": [
                        {
                            "resource_type": "network",
                            "operation": "receive",
                            "target": "https://ext-install.local:443",
                        },
                    ],
                },
                "runtime": {
                    "access": [
                        {
                            "resource_type": "network",
                            "operation": "receive",
                            "target": "https://ext-runtime.local:443",
                        },
                    ],
                },
            },
        )
    _write_manifest(base / "extractors", "x2", {"id": ""})

    monkeypatch.setattr(mod, "get_runtime_module_dirs", lambda: (str(builtin), str(user)))
    monkeypatch.setattr(mod, "get_runtime_engine_dirs", lambda: (str(base / "engines"),))
    monkeypatch.setattr(mod, "get_runtime_extractor_dirs", lambda: (str(base / "extractors"),))

    module_eps = mod.collect_module_endpoints()
    module_hosts = {e.host for e in module_eps}
    assert "a.local" in module_hosts
    assert "b.local" not in module_hosts  # duplicate module name skipped by seen_modules

    engine_eps = mod.collect_engine_endpoints(None)
    engine_hosts = {e.host for e in engine_eps}
    assert {"eng-install.local", "eng-runtime.local"}.issubset(engine_hosts)
    assert "x.local" not in engine_hosts

    extractor_eps = mod.collect_extractor_endpoints(None)
    extractor_hosts = {e.host for e in extractor_eps}
    assert extractor_hosts == {"ext-install.local", "ext-runtime.local"}

    monkeypatch.setattr(mod, "get_runtime_module_dirs", lambda: (str(builtin),))
    assert mod.collect_module_endpoints() == [NetworkEndpoint(host="a.local", port=443, protocol="tcp", source="module:moda", purpose="module_manifest")]


def test_collect_approvals_endpoints(monkeypatch):
    mod = importlib.import_module("democrai.core.infrastructure.sandbox.os.sources")

    monkeypatch.setattr(mod, "app_ctx", lambda: SimpleNamespace(db=None))
    assert mod.collect_access_policy_approval_endpoints(None) == []
    assert mod.collect_access_policy_session_approval_endpoints(None) == []

    approvals = [
        SimpleNamespace(resource_type="network", target="https://ok.local:443"),
        SimpleNamespace(resource_type="filesystem", target="/tmp"),
    ]
    out = mod.collect_access_policy_approval_endpoints(approvals)
    assert len(out) == 1 and out[0].host == "ok.local"

    reqs = [
        SimpleNamespace(resource_type="network", target="https://session.local:443"),
        SimpleNamespace(resource_type="dependency", target="x"),
    ]
    out2 = mod.collect_access_policy_session_approval_endpoints(reqs)
    assert len(out2) == 1 and out2[0].host == "session.local"

    monkeypatch.setattr(mod, "app_ctx", lambda: SimpleNamespace(db=object()))

    class _Query:
        def __init__(self, items):
            self.items = items

        def filter(self, *_args, **_kwargs):
            return self

        def all(self):
            return self.items

    class _Session:
        def __init__(self, items, boom=False):
            self.items = items
            self.boom = boom

        def __enter__(self):
            if self.boom:
                raise OperationalError("x", {}, None)
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def query(self, *_args, **_kwargs):
            return _Query(self.items)

    monkeypatch.setattr(
        mod,
        "SessionLocal",
        lambda: _Session([SimpleNamespace(resource_type="network", target="https://db-approval.local:443")]),
    )
    from_db = mod.collect_access_policy_approval_endpoints(None)
    assert len(from_db) == 1 and from_db[0].host == "db-approval.local"

    monkeypatch.setattr(
        mod,
        "SessionLocal",
        lambda: _Session([SimpleNamespace(resource_type="network", target="https://db-session.local:443")]),
    )
    from_db_session = mod.collect_access_policy_session_approval_endpoints(None)
    assert len(from_db_session) == 1 and from_db_session[0].host == "db-session.local"

    monkeypatch.setattr(mod, "SessionLocal", lambda: _Session([], boom=True))
    assert mod.collect_access_policy_approval_endpoints(None) == []
    assert mod.collect_access_policy_session_approval_endpoints(None) == []


def test_collect_mcp_server_endpoints(monkeypatch):
    mod = importlib.import_module("democrai.core.infrastructure.sandbox.os.sources")

    from_rows = mod.collect_mcp_server_endpoints(
        [
            {
                "name": "main",
                "enabled": True,
                "endpoint_url": "https://mcp.local:443/rpc",
            },
            {
                "name": "disabled",
                "enabled": False,
                "endpoint_url": "https://disabled.local:443/rpc",
            },
        ]
    )
    assert len(from_rows) == 1
    assert from_rows[0].host == "mcp.local"

    monkeypatch.setattr(mod, "app_ctx", lambda: SimpleNamespace(db=object()))

    class _Query:
        def __init__(self, items):
            self.items = items

        def filter(self, *_args, **_kwargs):
            return self

        def all(self):
            return self.items

    class _Session:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def query(self, *_args, **_kwargs):
            return _Query(
                [
                    SimpleNamespace(
                        name="db",
                        enabled=True,
                        endpoint_url="https://db-mcp.local:443/rpc",
                    )
                ]
            )

    monkeypatch.setattr(mod, "SessionLocal", lambda: _Session())
    from_db = mod.collect_mcp_server_endpoints(None)
    assert len(from_db) == 1 and from_db[0].host == "db-mcp.local"

    class _BoomSession:
        def __enter__(self):
            raise OperationalError("x", {}, None)

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(mod, "SessionLocal", lambda: _BoomSession())
    assert mod.collect_mcp_server_endpoints(None) == []


def test_sources_remaining_branches(monkeypatch):
    mod = importlib.import_module("democrai.core.infrastructure.sandbox.os.sources")

    monkeypatch.setattr(mod, "endpoint_from_target", lambda target, **_k: None if target == "bad-url" else NetworkEndpoint(host="h", port=1, protocol="tcp"))
    out = mod.collect_access_policy_approval_endpoints([SimpleNamespace(resource_type="network", target="bad-url")])
    assert out == []
    out2 = mod.collect_access_policy_session_approval_endpoints([SimpleNamespace(resource_type="network", target="bad-url")])
    assert out2 == []

    # vector host:port append branch in collect_config_endpoints
    monkeypatch.setattr(
        mod,
        "_host_port_endpoint",
        lambda host, port, **_k: NetworkEndpoint(host=str(host), port=int(port), protocol="tcp"),
    )
    cfg_values = {
        "storage.vector.type": "milvus",
        "storage.vector.host": "vector-host",
        "storage.vector.port": 19530,
        "storage.vector.url": None,
    }
    cfg = SimpleNamespace(get=lambda key, default=None: cfg_values.get(key, default))
    eps = mod.collect_config_endpoints(cfg)
    assert any(e.host == "vector-host" and e.port == 19530 for e in eps)

    # cover "endpoint is None" branches for all remote sections
    cfg_values_none = {
        "database.type": "postgres",
        "database.url": None,
        "database.data_type": "supabase",
        "database.data_url": None,
        "storage.media.type": "s3",
        "storage.media.endpoint_url": None,
        "storage.kg.type": "neo4j",
        "storage.kg.uri": None,
        "storage.vector.type": "milvus",
        "storage.vector.host": "",
        "storage.vector.port": 19530,
        "storage.vector.url": None,
        "storage.observability.type": "clickhouse",
        "storage.observability.url": None,
        "storage.observability.exporters.otlp.enabled": True,
        "storage.observability.exporters.otlp.endpoint": None,
        "network.redis.enabled": True,
        "network.redis.url": None,
        "session.redis.url": None,
        "session.ui_state.provider": "redis",
        "session.ui_state.url": None,
        "session.cache.provider": "redis",
    }
    cfg_none = SimpleNamespace(get=lambda key, default=None: cfg_values_none.get(key, default))
    assert mod.collect_config_endpoints(cfg_none) == []

    cfg_values_local_vector = dict(cfg_values_none)
    cfg_values_local_vector["storage.vector.type"] = "local"
    cfg_local_vector = SimpleNamespace(get=lambda key, default=None: cfg_values_local_vector.get(key, default))
    assert mod.collect_config_endpoints(cfg_local_vector) == []
