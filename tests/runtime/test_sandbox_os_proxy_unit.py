import pytest

from democrai.core.infrastructure.sandbox.os.proxy import OsSandboxConnectProxy
from democrai.core.infrastructure.sandbox.os.proxy import _endpoint_policy


def test_proxy_endpoint_policy_allows_exact_hosts_only():
    policy = _endpoint_policy(
        [
            {
                "host": "pypi.org",
                "port": 443,
                "protocol": "tcp",
            }
        ]
    )

    assert policy.allows("pypi.org", 443)
    assert policy.allows("PYPI.ORG", 443)
    assert not policy.allows("files.pythonhosted.org", 443)
    assert not policy.allows("pypi.org", 80)


def test_proxy_endpoint_policy_allows_manifest_wildcard_subdomains():
    policy = _endpoint_policy(
        [
            {
                "host": "*.modelscope.cn",
                "port": 443,
                "protocol": "tcp",
            }
        ]
    )

    assert policy.allows("cdn-lfs-cn-1.modelscope.cn", 443)
    assert not policy.allows("modelscope.cn", 443)
    assert not policy.allows("evilmodelscope.cn", 443)
    assert not policy.allows("cdn-lfs-cn-1.modelscope.cn", 80)


def test_proxy_endpoint_policy_ignores_invalid_wildcards():
    policy = _endpoint_policy(
        [
            {
                "host": "*",
                "port": 443,
                "protocol": "tcp",
            },
            {
                "host": "*.com",
                "port": 443,
                "protocol": "tcp",
            },
            {
                "host": "api.*.example.com",
                "port": 443,
                "protocol": "tcp",
            },
        ]
    )

    assert policy.count == 0
    assert not policy.allows("example.com", 443)
    assert not policy.allows("api.demo.example.com", 443)


def test_proxy_update_session_preserves_proxy_url_and_replaces_policy():
    proxy = OsSandboxConnectProxy()
    proxy._server = object()
    proxy._port = 4123

    created = proxy.create_session(
        endpoints=[
            {
                "host": "old.local",
                "port": 443,
                "protocol": "tcp",
            }
        ]
    )
    session = proxy._sessions[created["session_id"]]
    assert session.endpoints.allows("old.local", 443)

    updated = proxy.update_session(
        created["session_id"],
        endpoints=[
            {
                "host": "new.local",
                "port": 443,
                "protocol": "tcp",
            }
        ],
    )
    updated_session = proxy._sessions[created["session_id"]]

    assert updated["session_id"] == created["session_id"]
    assert updated["proxy_url"] == created["proxy_url"]
    assert updated_session.token == session.token
    assert not updated_session.endpoints.allows("old.local", 443)
    assert updated_session.endpoints.allows("new.local", 443)


def test_proxy_sessions_do_not_expire_by_time():
    proxy = OsSandboxConnectProxy()
    proxy._server = object()
    proxy._port = 4123

    created = proxy.create_session(endpoints=[])
    session = proxy._sessions[created["session_id"]]

    assert not hasattr(session, "expires_at")
    assert proxy.update_session(created["session_id"], endpoints=[]) == created


def test_proxy_update_session_fails_for_unknown_session():
    proxy = OsSandboxConnectProxy()

    with pytest.raises(RuntimeError, match="os_sandbox_proxy_session_not_found"):
        proxy.update_session("missing", endpoints=[])
