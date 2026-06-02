import socket

from democrai.core.infrastructure.network import targets as targets_mod


def test_normalize_and_split_helpers():
    assert targets_mod.normalize_network_target(" https://x ") == "https://x"
    assert targets_mod._split_netloc("example.com:443") == ("example.com", "443")
    assert targets_mod._split_netloc("[::1]:9000") == ("[::1]", "9000")
    assert targets_mod._split_netloc(":443") == (":443", None)
    assert targets_mod._normalize_host("[::1]") == "::1"


def test_parse_endpoint_target_and_pattern_matching(monkeypatch):
    assert targets_mod._parse_endpoint_target("https://example.com:443") == (
        "https",
        "example.com",
        443,
    )
    assert targets_mod._parse_endpoint_target("redis.local:6379") == (None, "redis.local", 6379)

    assert targets_mod._endpoint_pattern_matches(host="api.local", port=443, pattern="api.local")
    assert targets_mod._endpoint_pattern_matches(
        host="example.com",
        port=443,
        pattern="https://example.com:443",
        protocol="https",
    )

    monkeypatch.setattr(targets_mod, "_resolve_host_ips", lambda _h: ("1.2.3.4",))
    assert targets_mod._endpoint_pattern_matches(host="1.2.3.4", port=443, pattern="example.org")


def test_url_and_endpoint_allow_rules():
    assert targets_mod.is_network_target_allowed(
        "https://api.example.com/path",
        ["https://api.example.com/*"],
    )
    assert not targets_mod.is_network_target_allowed(
        "https://api.example.com/path",
        ["https://other.example.com/*"],
    )

    assert targets_mod.is_network_target_allowed("redis://cache.local:6379", ["redis://cache.local:6379"])
    assert not targets_mod.is_network_target_allowed("redis://cache.local:6379", ["redis://cache.local:6380"])


def test_targets_additional_branches(monkeypatch):
    assert targets_mod._hosts_for_match("") == []
    assert targets_mod._hosts_for_match("localhost") == ["localhost", "127.0.0.1", "::1"]
    assert targets_mod._hosts_for_match("::1") == ["::1", "localhost", "127.0.0.1"]
    assert targets_mod._resolve_host_ips("") == ()

    warnings = []
    monkeypatch.setattr(
        targets_mod,
        "app_ctx",
        lambda: type(
            "Ctx",
            (),
            {"logger": type("Logger", (), {"warning": lambda _self, msg: warnings.append(msg)})()},
        )(),
    )
    monkeypatch.setattr(
        targets_mod.socket,
        "getaddrinfo",
        lambda *_a, **_k: (_ for _ in ()).throw(socket.gaierror("dns")),
    )
    assert targets_mod._resolve_host_ips("x.invalid") == ()
    assert warnings and "DNS resolution failed" in warnings[-1]

    # malformed sockaddr entries are ignored
    monkeypatch.setattr(
        targets_mod.socket,
        "getaddrinfo",
        lambda *_a, **_k: [(None, None, None, None, "bad"), (None, None, None, None, ())],
    )
    assert targets_mod._resolve_host_ips("x.local") == ()
    with targets_mod._RESOLVED_IPS_LOCK:
        targets_mod._RESOLVED_IPS.clear()
        targets_mod._RESOLVED_IPS["stale.local"] = (0.0, ("1.1.1.1",))
    monkeypatch.setattr(
        targets_mod.socket,
        "getaddrinfo",
        lambda *_a, **_k: [(None, None, None, None, ("2.2.2.2", 0))],
    )
    assert targets_mod._resolve_host_ips("stale.local") == ("2.2.2.2",)
    with targets_mod._RESOLVED_IPS_LOCK:
        targets_mod._RESOLVED_IPS.clear()
        for i in range(257):
            targets_mod._RESOLVED_IPS[f"k{i}"] = (999999.0, ("1.1.1.1",))
    monkeypatch.setattr(
        targets_mod.socket,
        "getaddrinfo",
        lambda *_a, **_k: [(None, None, None, None, ("3.3.3.3", 0))],
    )
    _ = targets_mod._resolve_host_ips("new.local")
    with targets_mod._RESOLVED_IPS_LOCK:
        assert len(targets_mod._RESOLVED_IPS) <= 256
    monkeypatch.setattr(
        targets_mod.socket,
        "getaddrinfo",
        lambda *_a, **_k: [
            (None, None, None, None, ("", 0)),
            (None, None, None, None, ("4.4.4.4", 0)),
        ],
    )
    assert targets_mod._resolve_host_ips("mixed.local") == ("4.4.4.4",)

    assert targets_mod._endpoint_pattern_matches(host="x", port=1, pattern="") is False
    assert (
        targets_mod._endpoint_pattern_matches(
            host="example.com",
            port=443,
            pattern="http://example.com:443",
            protocol="https",
        )
        is True
    )
    assert (
        targets_mod._endpoint_pattern_matches(
            host="example.com",
            port=443,
            pattern="https://example.com:444",
            protocol="https",
        )
        is False
    )
    assert (
        targets_mod._endpoint_pattern_matches(
            host="8.8.8.8",
            port=53,
            pattern="dns.google",
            protocol=None,
        )
        is False
    )
    assert (
        targets_mod._endpoint_pattern_matches(
            host="example.com",
            port=80,
            pattern="tcp://",
            protocol="tcp",
        )
        is False
    )

    assert targets_mod.is_network_target_allowed("https://api.example.com/path", None) is False
    assert (
        targets_mod.is_network_target_allowed(
            "https://api.example.com/path",
            ["*.example.com:443"],
        )
        is True
    )
    assert targets_mod.is_network_target_allowed("bad-target", ["*.example.com"]) is False
    assert targets_mod.is_network_target_allowed("://", ["*:80"]) is False
