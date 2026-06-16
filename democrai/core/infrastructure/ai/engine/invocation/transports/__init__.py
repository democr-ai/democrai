__all__ = [
    "EngineOrchestratorClient",
    "EngineOrchestratorStatus",
    "EngineQueueTransport",
]


def __getattr__(name: str):
    if name in {"EngineOrchestratorClient", "EngineOrchestratorStatus"}:
        from democrai.core.infrastructure.ai.engine.invocation.transports.grpc import (
            EngineOrchestratorClient,
            EngineOrchestratorStatus,
        )

        return {
            "EngineOrchestratorClient": EngineOrchestratorClient,
            "EngineOrchestratorStatus": EngineOrchestratorStatus,
        }[name]
    if name == "EngineQueueTransport":
        from democrai.core.infrastructure.ai.engine.invocation.transports.queue import (
            EngineQueueTransport,
        )

        return EngineQueueTransport
    raise AttributeError(name)
