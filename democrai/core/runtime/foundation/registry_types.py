from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal


CommandLifecycle = Literal["callable", "schedule", "long_run", "single_run"]


@dataclass(frozen=True)
class ModuleCommandRegistration:
    name: str
    func: Callable
    lifecycle: CommandLifecycle
    module_name: str
    order: int
    handler_module: str
    handler_name: str
    cron: str | None = None
    interval_seconds: float | None = None
    restart_on_exit: bool = False


@dataclass(frozen=True)
class TemplateRegistration:
    name: str
    func: Callable
    priority: int
    order: int


@dataclass(frozen=True)
class HomePageRegistration:
    path: str
    priority: int
    order: int


@dataclass(frozen=True)
class NotificationCenterViewRegistration:
    path: str
    priority: int
    order: int
    module_name: str


@dataclass(frozen=True)
class RenderHookRegistration:
    name: str
    func: Callable
    priority: int
    order: int
    module_name: str


@dataclass(frozen=True)
class RenderHookDefinition:
    name: str
    module_name: str
    optional: bool
    description: str
    order: int


@dataclass(frozen=True)
class ModuleEventRegistration:
    name: str
    func: Callable
    priority: int
    order: int
    module_name: str


@dataclass(frozen=True)
class ModuleEventDefinition:
    name: str
    module_name: str
    params: tuple[str, ...]
    optional: bool
    description: str
    order: int
