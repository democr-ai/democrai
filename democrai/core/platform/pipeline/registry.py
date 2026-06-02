from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Optional

from .models import PipelineContext


@dataclass(frozen=True)
class PipelineHookRegistration:
    name: str
    func: Callable[[PipelineContext], Awaitable[Any]]
    priority: int
    order: int
    module_name: str


class PipelineHookRegistry:
    def __init__(self) -> None:
        self._hooks: Dict[str, list[PipelineHookRegistration]] = {}
        self._order = 0

    def register(
        self,
        name: str,
        func: Callable[[PipelineContext], Awaitable[Any]],
        *,
        priority: int = 0,
        module_name: str = "core",
    ) -> None:
        key = name.strip() if isinstance(name, str) else ""
        if not key:
            return
        resolved_module_name = (
            module_name.strip()
            if isinstance(module_name, str) and module_name.strip()
            else "core"
        )
        entries = self._hooks.setdefault(key, [])
        entries.append(
            PipelineHookRegistration(
                name=key,
                func=func,
                priority=int(priority),
                order=self._order,
                module_name=resolved_module_name,
            )
        )
        self._order += 1
        entries.sort(key=lambda item: (item.priority, item.order), reverse=True)

    def get(self, name: str) -> list[PipelineHookRegistration]:
        key = name.strip() if isinstance(name, str) else ""
        return list(self._hooks.get(key, []))

    def get_all(self, *, module_name: Optional[str] = None) -> list[PipelineHookRegistration]:
        items = [entry for values in self._hooks.values() for entry in values]
        if module_name is None:
            return items
        return [entry for entry in items if entry.module_name == module_name]


pipeline_hook_registry = PipelineHookRegistry()
