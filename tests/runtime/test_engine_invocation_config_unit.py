from __future__ import annotations

import pytest

from democrai.core.infrastructure.ai.engine.invocation.config import (
    EngineInvocationRuntimeConfig,
)
from democrai.core.infrastructure.ai.engine.invocation.orchestrator import (
    EngineOrchestratorProviderResolver,
)
from democrai.core.infrastructure.ai.engine.invocation.factory import (
    EngineOrchestratorProviderFactory,
)
from democrai.core.infrastructure.ai.engine.invocation.queue.config import (
    engine_response_stream_key,
)
from democrai.core.infrastructure.ai.engine.response.factory import (
    EngineResponseStreamFactory,
)
import democrai.core.infrastructure.ai.engine.invocation.factory as invocation_factory
import democrai.core.infrastructure.ai.engine.response.factory as response_factory
import democrai.core.runtime.bootstrap.config_validation as config_validation


class _Provider:
    def __init__(self, values: dict):
        self.values = values

    def get(self, key, default=None):
        return self.values.get(key, default)


_NODE_COORDINATION_OK = {
    "ai.engine_orchestrator.node_coordination.enabled": True,
    "database.type": "postgres",
    "network.node_id": "node-a",
}


def _base_valid_config() -> dict:
    return {
        "auth.jwt_secret": "a-very-long-and-random-secret-for-tests",
    }


def test_node_coordination_disabled_by_default():
    assert EngineInvocationRuntimeConfig.load(None).node_coordination_enabled is False
    assert (
        EngineInvocationRuntimeConfig.load(_Provider({})).node_coordination_enabled
        is False
    )


def test_runtime_config_defaults():
    loaded = EngineInvocationRuntimeConfig.load(_Provider({}))
    assert loaded.queue_claim_poll_seconds == 2.0
    assert loaded.queue_lease_seconds == 120
    assert loaded.queue_max_attempts == 3
    assert loaded.placement_force_claim_age_seconds == 10.0
    assert loaded.node_state_active_threshold_seconds == 10.0
    assert loaded.node_state_publish_seconds == 2.0
    assert loaded.queue_keepalive_seconds == 10.0
    assert loaded.queue_retention_seconds == 86400


def test_runtime_config_overrides_and_floors():
    loaded = EngineInvocationRuntimeConfig.load(
        _Provider(
            {
                "ai.engine_orchestrator.queue.claim_poll_seconds": 0.01,
                "ai.engine_orchestrator.queue.lease_seconds": 1,
                "ai.engine_orchestrator.queue.max_attempts": 0,
            }
        )
    )
    assert loaded.queue_claim_poll_seconds == 0.1
    assert loaded.queue_lease_seconds == 5
    assert loaded.queue_max_attempts == 1


def test_response_stream_key():
    assert engine_response_stream_key("abc123") == "democrai:engine:resp:abc123"


def test_validate_node_coordination_noop_when_disabled():
    EngineInvocationRuntimeConfig.load(_Provider({})).validate_node_coordination(
        _Provider({})
    )
    EngineInvocationRuntimeConfig.load(None).validate_node_coordination(None)


def test_validate_node_coordination_ok():
    loaded = EngineInvocationRuntimeConfig.load(_Provider(dict(_NODE_COORDINATION_OK)))
    loaded.validate_node_coordination(_Provider(dict(_NODE_COORDINATION_OK)))


@pytest.mark.parametrize(
    ("missing_key", "expected_fragment"),
    [
        ("database.type", "database.type=postgres"),
        ("network.node_id", "network.node_id"),
    ],
)
def test_validate_node_coordination_missing_prerequisite(
    missing_key, expected_fragment
):
    values = dict(_NODE_COORDINATION_OK)
    if missing_key == "database.type":
        values["database.type"] = "sqlite"
    else:
        values.pop(missing_key)
    loaded = EngineInvocationRuntimeConfig.load(_Provider(values))
    with pytest.raises(RuntimeError) as excinfo:
        loaded.validate_node_coordination(_Provider(values))
    message = str(excinfo.value)
    assert message.startswith("engine_orchestrator_node_coordination_config_invalid:")
    assert expected_fragment in message


def test_validate_node_coordination_reports_all_problems():
    provider = _Provider({"ai.engine_orchestrator.node_coordination.enabled": True})
    loaded = EngineInvocationRuntimeConfig.load(provider)
    with pytest.raises(RuntimeError) as excinfo:
        loaded.validate_node_coordination(provider)
    message = str(excinfo.value)
    assert "database.type=postgres" in message
    assert "network.node_id" in message


def test_config_validation_node_coordination_missing_prerequisites():
    values = _base_valid_config()
    values["ai.engine_orchestrator.node_coordination.enabled"] = True
    values["database.type"] = "sqlite"
    result = config_validation.validate_config_provider(
        _Provider(values), config_path="/tmp/cfg.yml"
    )
    messages = [issue.message for issue in result.errors]
    assert any("database.type=postgres" in message for message in messages)
    assert any("network.node_id" in message for message in messages)


def test_validate_node_coordination_threshold_vs_publish():
    values = dict(_NODE_COORDINATION_OK)
    values["ai.engine_orchestrator.node_state.publish_seconds"] = 30
    values["ai.engine_orchestrator.node_state.active_threshold_seconds"] = 10
    loaded = EngineInvocationRuntimeConfig.load(_Provider(values))
    with pytest.raises(RuntimeError, match="at least twice"):
        loaded.validate_node_coordination(_Provider(values))


def test_config_validation_queue_provider_requires_cross_process_response_stream():
    values = _base_valid_config()
    values.update(
        {
            "ai.engine_orchestrator.provider.type": "queue",
            "ai.engine_orchestrator.response_stream.type": "memory",
        }
    )
    result = config_validation.validate_config_provider(
        _Provider(values), config_path="/tmp/cfg.yml"
    )
    assert any(
        "response_stream.type must be a cross-process provider" in issue.message
        for issue in result.errors
    )


def test_config_validation_queue_provider_accepts_registered_shared_stream():
    values = _base_valid_config()
    values.update(
        {
            "ai.engine_orchestrator.provider.type": "queue",
            "ai.engine_orchestrator.response_stream.type": "redis",
        }
    )
    result = config_validation.validate_config_provider(
        _Provider(values), config_path="/tmp/cfg.yml"
    )
    assert result.ok, [issue.message for issue in result.errors]


def test_config_validation_uses_registry_metadata_without_importing_providers(
    monkeypatch,
):
    def fail_import(module_name):
        raise AssertionError(f"provider module imported during validation: {module_name}")

    monkeypatch.setattr(invocation_factory, "import_module", fail_import)
    monkeypatch.setattr(response_factory, "import_module", fail_import)
    values = _base_valid_config()
    values.update(
        {
            "ai.engine_orchestrator.provider.type": "queue",
            "ai.engine_orchestrator.response_stream.type": "redis",
        }
    )

    result = config_validation.validate_config_provider(
        _Provider(values), config_path="/tmp/cfg.yml"
    )

    assert result.ok, [issue.message for issue in result.errors]


def test_engine_response_stream_factory_uses_engine_redis_provider():
    values = {
        "ai.engine_orchestrator.response_stream.type": "redis",
        "ai.engine_orchestrator.response_stream.maxlen": 128,
        "ai.engine_orchestrator.response_stream.ttl_seconds": 120,
    }
    stream = EngineResponseStreamFactory.get_stream(_Provider(values))
    assert stream.__class__.__name__ == "RedisEngineResponseStream"


def test_engine_orchestrator_provider_factory_accepts_import_path():
    provider_type = (
        "democrai.core.infrastructure.ai.engine.invocation.transports.queue:"
        "EngineQueueTransport"
    )

    assert EngineOrchestratorProviderFactory.has_provider(provider_type) is True
    assert EngineOrchestratorProviderFactory.receiver_names(provider_type) == ("queue",)


def test_config_validation_queue_provider_rejects_unknown_response_stream():
    values = _base_valid_config()
    values.update(
        {
            "ai.engine_orchestrator.provider.type": "queue",
            "ai.engine_orchestrator.response_stream.type": "missing-provider",
        }
    )
    result = config_validation.validate_config_provider(
        _Provider(values), config_path="/tmp/cfg.yml"
    )
    assert any(
        "response_stream.type is not a registered engine response stream provider"
        in issue.message
        for issue in result.errors
    )


def test_config_validation_node_coordination_ok_with_local_media_warns():
    values = _base_valid_config()
    values.update(
        {
            "ai.engine_orchestrator.node_coordination.enabled": True,
            "database.type": "postgres",
            "database.url": "postgresql://u:p@db:5432/democrai",
            "network.node_id": "node-a",
            "storage.media.type": "local",
        }
    )
    result = config_validation.validate_config_provider(
        _Provider(values), config_path="/tmp/cfg.yml"
    )
    assert result.ok, [issue.message for issue in result.errors]
    assert any("shared mount" in issue.message for issue in result.warnings)


def test_config_validation_node_coordination_disabled_adds_nothing():
    values = _base_valid_config()
    result = config_validation.validate_config_provider(
        _Provider(values), config_path="/tmp/cfg.yml"
    )
    assert result.ok, [issue.message for issue in result.errors]
    assert not any("node_coordination" in issue.message for issue in result.warnings)


def test_legacy_invocation_provider_config_is_rejected():
    values = {
        "ai.engine_orchestrator.invocation.provider": "queue",
    }
    with pytest.raises(RuntimeError, match="legacy_provider_config"):
        EngineOrchestratorProviderResolver.provider_name_from_config(
            _Provider(values)
        )
