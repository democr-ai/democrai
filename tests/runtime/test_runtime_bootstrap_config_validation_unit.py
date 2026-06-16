from __future__ import annotations

import json
from types import SimpleNamespace

import democrai.core.runtime.bootstrap.config_validation as mod


class _Provider:
    def __init__(self, values: dict):
        self.values = values

    def get(self, key, default=None):
        return self.values.get(key, default)


def test_validate_config_provider_invalid_and_output(monkeypatch, capsys):
    monkeypatch.setenv("PINECONE_API_KEY", "")
    monkeypatch.setattr(mod, "validate_timezone_name", lambda _v: False)

    provider = _Provider(
        {
            "database.type": "bad",
            "database.data_type": "supabase",
            "storage.media.type": "s3",
            "storage.kg.type": "neo4j",
            "storage.vector.type": "pinecone",
            "storage.observability.type": "clickhouse",
            "session.identity.provider": "redis",
            "session.ui_state.provider": "postgres",
            "session.cache.provider": "redis",
            "network.ws.codec": "xml",
            "http.client_ip.mode": "spoof",
            "http.client_ip.trusted_proxies": ["bad-cidr"],
            "modules.trust_mode": "invalid",
            "modules.allow_user_modules": "maybe",
            "modules.trusted_modules": 5,
            "session.cache.ttl_seconds": "abc",
            "storage.media.remote_cache.ttl_seconds": "-1",
            "session.idle_ttl_seconds": "0",
            "session.absolute_ttl_seconds": "abc",
            "auth.cookie_secure": "maybe",
            "auth.cookie_http_only": "maybe",
            "auth.cookie_samesite": "bad",
            "auth.jwt_issuer": " ",
            "auth.jwt_audience": "",
            "auth.jwt_tid": "",
            "auth.jwt_access_ttl_seconds": "0",
            "auth.login_rate_limit.enabled": "maybe",
            "auth.login_rate_limit.username.max_failures": "0",
            "auth.login_rate_limit.ip.window_seconds": "abc",
            "http.cors.enabled": True,
            "http.cors.allow_origins": ["*"],
            "http.cors.allow_credentials": True,
            "app.timezone": "Bad/Zone",
            "storage.media.access_key": "AK",
            "storage.observability.exporters.otlp.enabled": True,
            "auth.jwt_secret": "change-me-with-a-long-random-secret",
            "network.redis.enabled": True,
            "session.redis.url": None,
            "network.redis.url": None,
        }
    )

    result = mod.validate_config_provider(provider, config_path="/tmp/cfg.yml")
    assert result.ok is False
    assert result.errors
    assert result.warnings
    payload = result.to_dict()
    assert payload["ok"] is False
    assert payload["config_path"] == "/tmp/cfg.yml"

    assert mod.print_validation_result(result) == 1
    out = capsys.readouterr().out
    assert "[CONFIG] path=" in out
    assert "[ERROR]" in out

    assert mod.print_validation_result_json(result) == 1
    json_out = capsys.readouterr().out
    assert json.loads(json_out)["ok"] is False


def test_validate_config_provider_valid_paths_and_file(monkeypatch, tmp_path):
    monkeypatch.setattr(mod, "validate_timezone_name", lambda _v: True)
    values = {
        "database.type": "postgres",
        "database.url": "postgres://x",
        "database.data_type": "postgres",
        "database.data_url": "postgres://x",
        "storage.media.type": "local",
        "storage.kg.type": "ladybug",
        "storage.vector.type": "sqlite-vec",
        "storage.observability.type": "sqlite",
        "session.identity.provider": "sqlite",
        "session.ui_state.provider": "sqlite",
        "session.cache.provider": "memory",
        "network.ws.codec": "json",
        "http.client_ip.mode": "trusted_proxy",
        "http.client_ip.trusted_proxies": ["10.0.0.0/8", "127.0.0.1"],
        "modules.trust_mode": "all",
        "modules.allow_user_modules": True,
        "modules.trusted_modules": ["a", "b"],
        "session.cache.ttl_seconds": 10,
        "storage.media.remote_cache.ttl_seconds": 20,
        "session.idle_ttl_seconds": 1,
        "session.absolute_ttl_seconds": 1,
        "session.cleanup_interval_seconds": 1,
        "storage.observability.retention.events_days": 1,
        "storage.observability.retention.audit_days": 1,
        "storage.observability.retention.llm_usage_days": 1,
        "storage.observability.retention.export_outbox_days": 1,
        "storage.observability.retention.cleanup_interval_seconds": 1,
        "storage.observability.exporters.outbox.flush_interval_seconds": 1,
        "auth.cookie_secure": True,
        "auth.cookie_http_only": False,
        "auth.cookie_samesite": "lax",
        "auth.jwt_issuer": "iss",
        "auth.jwt_audience": "aud",
        "auth.jwt_tid": "tid",
        "auth.jwt_access_ttl_seconds": 1,
        "auth.login_rate_limit.enabled": True,
        "auth.login_rate_limit.username.max_failures": 5,
        "auth.login_rate_limit.username.window_seconds": 300,
        "auth.login_rate_limit.username.lockout_seconds": 900,
        "auth.login_rate_limit.ip.max_failures": 20,
        "auth.login_rate_limit.ip.window_seconds": 300,
        "auth.login_rate_limit.ip.lockout_seconds": 900,
        "http.cors.enabled": False,
        "http.cors.allow_credentials": False,
        "app.timezone": "UTC",
        "auth.jwt_secret": "super-secret",
    }
    provider = _Provider(values)
    result = mod.validate_config_provider(provider, config_path="/tmp/ok.yml")
    assert result.ok is True
    assert result.errors == []

    monkeypatch.setattr(mod, "get_data_dir", lambda: str(tmp_path))
    monkeypatch.setattr(mod, "YamlConfigProvider", lambda path: provider)
    file_result = mod.validate_config_file(None)
    assert file_result.ok is True
    assert file_result.config_path.endswith("config.yaml")

    explicit_result = mod.validate_config_file("/x/custom.yaml")
    assert explicit_result.config_path == "/x/custom.yaml"


def test_validate_config_provider_additional_branch_coverage(monkeypatch):
    monkeypatch.setenv("PINECONE_API_KEY", "token")
    monkeypatch.setattr(mod, "validate_timezone_name", lambda _v: True)

    base = {
        "database.type": "sqlite",
        "database.data_type": "sqlite",
        "storage.media.type": "local",
        "storage.kg.type": "ladybug",
        "storage.vector.type": "sqlite-vec",
        "storage.observability.type": "sqlite",
        "session.identity.provider": "sqlite",
        "session.ui_state.provider": "sqlite",
        "session.cache.provider": "memory",
        "network.ws.codec": "json",
        "modules.trust_mode": "all",
        "auth.jwt_secret": "valid-secret",
    }

    case_true = _Provider(
        {
            **base,
            "session.cache.ttl_seconds": "0",
            "storage.media.remote_cache.ttl_seconds": "abc",
            "auth.jwt_access_ttl_seconds": "abc",
            "http.cors.enabled": "true",
            "http.cors.allow_credentials": "false",
            "http.cors.allow_origins": "https://a.test, https://b.test",
        }
    )
    result_true = mod.validate_config_provider(case_true)
    assert any("session.cache.ttl_seconds must be > 0" in issue.message for issue in result_true.errors)
    assert any("storage.media.remote_cache.ttl_seconds must be an integer" in issue.message for issue in result_true.errors)
    assert any("auth.jwt_access_ttl_seconds must be an integer" in issue.message for issue in result_true.errors)

    case_false = _Provider(
        {
            **base,
            "http.cors.enabled": "false",
            "http.cors.allow_credentials": "true",
            "http.cors.allow_origins": "*",
        }
    )
    result_false = mod.validate_config_provider(case_false)
    assert any("allow_origins cannot contain '*'" in issue.message for issue in result_false.errors)

    case_invalid = _Provider(
        {
            **base,
            "http.cors.enabled": "invalid",
            "http.cors.allow_credentials": "invalid",
        }
    )
    result_invalid = mod.validate_config_provider(case_invalid)
    assert any("http.cors.enabled must be a boolean" in issue.message for issue in result_invalid.errors)
    assert any("http.cors.allow_credentials must be a boolean" in issue.message for issue in result_invalid.errors)
