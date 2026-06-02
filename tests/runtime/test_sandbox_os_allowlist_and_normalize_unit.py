from democrai.core.infrastructure.sandbox.os.allowlist import build_application_network_allowlist
from democrai.core.infrastructure.sandbox.os.models import NetworkEndpoint
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
