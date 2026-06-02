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
