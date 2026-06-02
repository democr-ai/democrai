from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


NodeKind = Literal[
    "tool",
    "agent",
    "condition",
    "transform",
    "channel_send",
    "parallel",
]


@dataclass(frozen=True)
class WorkflowNodeOutputDefinition:
    id: str

    when: str | None = None
    next_node: str | None = None
    input_map: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class WorkflowNodeDefinition:
    id: str
    kind: NodeKind

    target: str | None = None
    input_map: dict[str, str] = field(default_factory=dict)
    output_key: str | None = None
    outputs: tuple[WorkflowNodeOutputDefinition, ...] = ()
    default_output: str | None = None

    condition_expr: str | None = None
    on_true: str | None = None
    on_false: str | None = None

    parallel_nodes: tuple[str, ...] = ()
    channel_id: str | None = None

    max_retries: int = 0
    retry_delay_seconds: float = 1.0
    optional: bool = False
    next_node: str | None = None


@dataclass(frozen=True)
class WorkflowDefinition:
    id: str
    name: str
    description: str
    module_name: str = "core"

    trigger: str = ""
    cron: str | None = None

    entry_node: str = ""
    nodes: tuple[WorkflowNodeDefinition, ...] = ()

    background: bool = True
    timeout_seconds: float = 300.0
    max_parallel_instances: int = 1
