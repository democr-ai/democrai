from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, AsyncIterator


@dataclass(frozen=True)
class EngineInvocationRequest:
    method: str
    payload: dict[str, Any] | None = None
    request_id: str | None = None
    security_context: dict[str, Any] | None = None


@dataclass(frozen=True)
class EngineInvocationTarget:
    selector_type: str
    model_registry_id: int | None = None
    objective: str | None = None
    capability: str | None = None
    capabilities: tuple[str, ...] = ()
    prefer_local: bool | None = None
    confirm_swap: bool = False


@dataclass(frozen=True)
class EngineOrchestratorStatus:
    ok: bool
    node_id: str
    pid: int
    started_at: str
    active_instances_json: str
    active_jobs_json: str


class EngineInvocationProvider(ABC):
    @abstractmethod
    async def invoke(self, request: EngineInvocationRequest) -> Any:
        raise NotImplementedError

    @abstractmethod
    def invoke_stream(
        self,
        request: EngineInvocationRequest,
        *,
        on_message: Any = None,
    ) -> AsyncIterator[Any]:
        raise NotImplementedError

    @abstractmethod
    async def cancel(self, request_id: str) -> bool:
        raise NotImplementedError


class EngineOrchestratorProvider(ABC):
    requires_media_storage_refs = False

    @abstractmethod
    async def invoke(
        self,
        target: EngineInvocationTarget,
        request: EngineInvocationRequest,
    ) -> Any:
        raise NotImplementedError

    @abstractmethod
    def invoke_stream(
        self,
        target: EngineInvocationTarget,
        request: EngineInvocationRequest,
        *,
        on_message: Any = None,
    ) -> AsyncIterator[Any]:
        raise NotImplementedError

    @abstractmethod
    async def cancel(self, request_id: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def cancel_sync(self, request_id: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def status(self, *, timeout: float | None = None) -> EngineOrchestratorStatus:
        raise NotImplementedError

    @abstractmethod
    def list_active_jobs(
        self,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def health_check(self, *, timeout: float | None = None) -> bool:
        raise NotImplementedError

    @abstractmethod
    def wait_ready(self, *, timeout: float) -> EngineOrchestratorStatus:
        raise NotImplementedError

    @abstractmethod
    def refresh_registries(self, *, reason: str = "") -> bool:
        raise NotImplementedError

    @abstractmethod
    def sync_active_engines(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def unload_model(
        self,
        *,
        engine_registry_id: int | str,
        model_registry_id: int | str,
    ) -> bool:
        raise NotImplementedError

    @abstractmethod
    def stop_engine(self, *, engine_registry_id: int | str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def invoke_engine_action(
        self,
        *,
        engine_registry_id: int | str,
        engine_id: str,
        config: dict[str, Any] | None,
        method: str,
        payload: dict[str, Any] | None = None,
    ) -> Any:
        raise NotImplementedError

    @abstractmethod
    def invoke_engine_runtime(
        self,
        *,
        engine_registry_id: int | str,
        engine_id: str,
        config: dict[str, Any] | None,
        method: str,
        model_registry_id: int | str,
        payload: dict[str, Any] | None = None,
    ) -> Any:
        raise NotImplementedError
