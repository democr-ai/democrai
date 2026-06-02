from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal

from democrai.core.application.access_policy import AccessManifestRule
from democrai.core.application.ai.engine.schemas.completion import Function
from democrai.core.application.ai.engine.schemas.completion import Tool


@dataclass
class SkillMetadata:
    name: str
    description: str
    title: str = ""
    summary: str = ""
    tags: tuple[str, ...] = ()
    input_hint: str = ""
    usage: str = ""
    examples: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    outputs: tuple[str, ...] = ()
    version: str = ""
    author: str = ""
    homepage: str = ""
    allowed_tools: tuple[str, ...] = ()
    asset_paths: tuple[str, ...] = ()
    script_paths: tuple[str, ...] = ()
    module_name: str = ""
    path: str = ""
    access: list[AccessManifestRule] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SkillDefinition:
    metadata: SkillMetadata
    content: str
    root_dir: Path

    @property
    def assets_dir(self) -> Path:
        return self.root_dir / "assets"

    def has_assets(self) -> bool:
        return bool(self.metadata.asset_paths)


@dataclass
class AgentToolDefinition:
    name: str
    func: Callable[..., Any]
    description: str
    input_schema: dict[str, Any]
    module_name: str = "core"
    confirmation_required: bool = False
    access: list[AccessManifestRule] = field(default_factory=list)
    title: str = ""
    user_selectable: bool = True

    def to_completion_tool(self) -> Tool:
        return Tool(
            function=Function(
                name=self.name,
                description=self.description,
                parameters=self.input_schema or {"type": "object", "properties": {}},
            )
        )


@dataclass
class AgentDefinition:
    name: str
    description: str
    objective: str = "chat"
    system_prompt: str = ""
    tools: tuple[str, ...] = ()
    skills: tuple[str, ...] = ()
    max_iterations: int = 3
    module_name: str = "core"
    handler: Callable[..., Any] | None = None
    access: list[AccessManifestRule] = field(default_factory=list)
    mcp_servers: tuple[str, ...] = ()
    title: str = ""


@dataclass(frozen=True)
class PipelineStepDefinition:
    kind: Literal["agent", "tool", "parallel"]
    target: str = ""
    output_key: str = "result"
    input_key: str | None = None
    input_template: str | None = None
    arguments: dict[str, Any] = field(default_factory=dict)
    steps: tuple["PipelineStepDefinition", ...] = ()
    error_policy: Literal["fail_fast", "collect_errors"] = "fail_fast"
    max_concurrency: int | None = None


@dataclass
class PipelineDefinition:
    name: str
    description: str
    steps: tuple[PipelineStepDefinition, ...]
    module_name: str = "core"
    access: list[AccessManifestRule] = field(default_factory=list)


@dataclass(frozen=True)
class AgentRunResult:
    agent_name: str
    content: str
    tool_results: tuple[dict[str, Any], ...] = ()
    activated_skills: tuple[str, ...] = ()
    raw_response: Any = None
    usage_report: tuple[dict[str, Any], ...] = ()
