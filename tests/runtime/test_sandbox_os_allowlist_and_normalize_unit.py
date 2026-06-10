from democrai.core.infrastructure.sandbox.os.allowlist import (
    NetworkPolicyRequest,
    build_application_network_allowlist,
    build_subject_network_allowlist,
    direct_enforcement_allowlist,
)
from democrai.core.infrastructure.sandbox.os.models import (
    ApplicationNetworkAllowlist,
    NetworkEndpoint,
)
from democrai.core.infrastructure.sandbox.os.normalize import (
    _normalize_host,
    _normalize_port,
    dedupe_endpoints,
    endpoint_from_target,
    normalize_endpoint,
)


def test_normalize_host_and_port():
    assert _normalize_host(" EXAMPLE.COM ") == "example.com"
    assert _normalize_host("[::1]") == "[::1]"
    assert _normalize_port("443") == 443
    assert _normalize_port(0) is None
    assert _normalize_port("abc") is None


def test_normalize_endpoint_and_dedupe():
    ep = normalize_endpoint(NetworkEndpoint(host=" API.LOCAL ", port="443", protocol="TCP"))
    assert ep is not None
    assert ep.host == "api.local"
    assert ep.port == 443
    assert ep.protocol == "tcp"

    endpoints = [
        NetworkEndpoint(host="api.local", port=443, protocol="tcp"),
        NetworkEndpoint(host="api.local", port=443, protocol="tcp"),
        NetworkEndpoint(host="api.local", port=8443, protocol="tcp"),
        NetworkEndpoint(host="", port=8443, protocol="tcp"),
    ]
    deduped = dedupe_endpoints(endpoints)
    assert len(deduped) == 2


def test_endpoint_from_target_for_url_and_host_port():
    url_ep = endpoint_from_target("https://example.com/path", source="cfg", purpose="api")
    assert url_ep is not None
    assert url_ep.host == "example.com"
    assert url_ep.port == 443
    assert url_ep.source == "cfg"

    host_ep = endpoint_from_target("redis://cache.local:6379")
    assert host_ep is not None
    assert host_ep.host == "cache.local"
    assert host_ep.port == 6379

    assert endpoint_from_target("notaurl") is None


def test_build_application_network_allowlist_collects_and_dedupes(monkeypatch):
    monkeypatch.setattr(
        "democrai.core.infrastructure.sandbox.os.allowlist.collect_config_endpoints",
        lambda _config: [NetworkEndpoint(host="api.local", port=443, source="cfg")],
    )
    monkeypatch.setattr(
        "democrai.core.infrastructure.sandbox.os.allowlist.collect_module_endpoints",
        lambda _modules: [NetworkEndpoint(host="api.local", port=443, source="mod")],
    )
    monkeypatch.setattr("democrai.core.infrastructure.sandbox.os.allowlist.collect_engine_endpoints", lambda _engines: [])
    monkeypatch.setattr("democrai.core.infrastructure.sandbox.os.allowlist.collect_mcp_server_endpoints", lambda _mcp_servers: [])
    monkeypatch.setattr("democrai.core.infrastructure.sandbox.os.allowlist.collect_extractor_endpoints", lambda _extractors: [])
    monkeypatch.setattr("democrai.core.infrastructure.sandbox.os.allowlist.collect_access_policy_approval_endpoints", lambda _items: [])
    monkeypatch.setattr("democrai.core.infrastructure.sandbox.os.allowlist.collect_access_policy_session_approval_endpoints", lambda _items: [])
    monkeypatch.setattr("democrai.core.infrastructure.sandbox.os.allowlist.collect_observed_endpoints", lambda _config: [])
    monkeypatch.setattr("democrai.core.infrastructure.sandbox.os.allowlist.debug_os_sandbox_flow", lambda *a, **k: None)

    allowlist = build_application_network_allowlist(config=object(), modules=object())
    assert len(allowlist.endpoints) == 1
    assert allowlist.endpoints[0].host == "api.local"


def test_build_subject_network_allowlist_filters_engine_phase(monkeypatch):
    monkeypatch.setattr(
        "democrai.core.infrastructure.sandbox.os.allowlist.collect_engine_endpoints",
        lambda _engines: [
            NetworkEndpoint(host="install.local", port=443, source="engine:onnx", purpose="engine_install_manifest"),
            NetworkEndpoint(host="runtime.local", port=443, source="engine:onnx", purpose="engine_runtime_manifest"),
            NetworkEndpoint(host="other.local", port=443, source="engine:yolo", purpose="engine_install_manifest"),
        ],
    )
    monkeypatch.setattr("democrai.core.infrastructure.sandbox.os.allowlist._approval_endpoints_for_subject", lambda *a, **k: [])
    monkeypatch.setattr("democrai.core.infrastructure.sandbox.os.allowlist.debug_os_sandbox_flow", lambda *a, **k: None)

    allowlist = build_subject_network_allowlist(
        NetworkPolicyRequest(
            scope="engine_install",
            subject_kind="engine",
            subject_id="onnx",
            phase="install",
        )
    )

    assert [(item.host, item.source, item.purpose) for item in allowlist.endpoints] == [
        ("install.local", "engine:onnx", "engine_install_manifest")
    ]


def test_build_subject_network_allowlist_skill_inherits_only_module(monkeypatch):
    monkeypatch.setattr(
        "democrai.core.infrastructure.sandbox.os.allowlist.collect_module_endpoints",
        lambda _modules: [
            NetworkEndpoint(host="system.local", port=443, source="module:system", purpose="module_manifest"),
            NetworkEndpoint(host="other.local", port=443, source="module:other", purpose="module_manifest"),
        ],
    )
    monkeypatch.setattr("democrai.core.infrastructure.sandbox.os.allowlist._approval_endpoints_for_subject", lambda *a, **k: [])
    monkeypatch.setattr("democrai.core.infrastructure.sandbox.os.allowlist.debug_os_sandbox_flow", lambda *a, **k: None)

    allowlist = build_subject_network_allowlist(
        NetworkPolicyRequest(
            scope="skill_runtime",
            subject_kind="skill",
            subject_id="system.demo",
            subject_chain=({"kind": "module", "name": "system"},),
            inheritance_mode="parent_subject",
        )
    )

    assert [(item.host, item.source) for item in allowlist.endpoints] == [
        ("system.local", "module:system")
    ]


def test_direct_enforcement_allowlist_keeps_only_direct_endpoints():
    allowlist = ApplicationNetworkAllowlist(
        endpoints=[
            NetworkEndpoint(host="db.local", port=5432, source="config.database", purpose="database"),
            NetworkEndpoint(host="redis.local", port=6379, source="config.network_redis", purpose="redis"),
            NetworkEndpoint(host="mcp.local", port=8080, source="mcp:tools", purpose="mcp_runtime"),
            NetworkEndpoint(host="huggingface.co", port=443, source="engine:vllm", purpose="engine_install_manifest"),
            NetworkEndpoint(host="cdn-lfs.huggingface.co", port=443, source="observed", purpose="observed"),
            NetworkEndpoint(host="api.example.com", port=443, source="module:demo", purpose="module_manifest"),
        ]
    )

    filtered = direct_enforcement_allowlist(allowlist)

    assert [(item.host, item.source) for item in filtered.endpoints] == [
        ("db.local", "config.database"),
        ("redis.local", "config.network_redis"),
        ("mcp.local", "mcp:tools"),
    ]
