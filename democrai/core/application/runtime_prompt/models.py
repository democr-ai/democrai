from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RuntimePromptAction:
    id: str
    label: str
    required_permissions: tuple[str, ...] = ()


@dataclass(frozen=True)
class RuntimePromptRequest:
    prompt_id: str
    question: str
    actions: tuple[RuntimePromptAction, ...]
    user_id: int
    organization_id: int | None
    session_key: str
    request_id: str
    role: str | None = None
    access_level: int | None = None
    required_role: str | None = None
    required_access_level: int | None = None
    required_permissions: tuple[str, ...] = ()
    form_model: tuple[dict[str, Any], ...] = ()
    form_values: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    timeout_seconds: float = 300.0


@dataclass(frozen=True)
class RuntimePromptDecision:
    ok: bool
    prompt_id: str
    action: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "ok": self.ok,
            "prompt_id": self.prompt_id,
        }
        if self.action is not None:
            payload["action"] = self.action
        if self.data:
            payload["data"] = dict(self.data)
        if self.error is not None:
            payload["error"] = self.error
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        return payload


@dataclass
class PendingRuntimePrompt:
    request: RuntimePromptRequest
    future: asyncio.Future[RuntimePromptDecision]
