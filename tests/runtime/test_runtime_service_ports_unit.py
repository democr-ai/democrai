from __future__ import annotations

from types import SimpleNamespace

from democrai.core.application.ai.engine.orchestrator.config import orchestrator_port
from democrai.core.application.knowledge.query.config import knowledge_query_port
from democrai.core.application.runtime_prompt.grpc.config import runtime_prompt_port


def _config(values: dict[str, int] | None = None):
    values = values or {}
    return SimpleNamespace(get=lambda key, default=None: values.get(key, default))


def test_runtime_service_ports_default_to_windows_allowed_range():
    assert orchestrator_port(_config()) == 40151
    assert runtime_prompt_port(_config()) == 40152
    assert knowledge_query_port(_config()) == 40153


def test_runtime_service_ports_accept_explicit_config_values():
    config = _config(
        {
            "ai.engine_orchestrator.port": 41051,
            "runtime_prompt.port": 41052,
            "knowledge.query_service.port": 41053,
        }
    )

    assert orchestrator_port(config) == 41051
    assert runtime_prompt_port(config) == 41052
    assert knowledge_query_port(config) == 41053
