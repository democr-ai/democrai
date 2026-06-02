from __future__ import annotations

import importlib
from typing import Any, Callable

from democrai.core.application.access_policy import AccessManifestRule
from democrai.core.platform.agents.models import AgentDefinition
from democrai.core.platform.agents.models import AgentToolDefinition
from democrai.core.platform.agents.models import PipelineDefinition
from democrai.core.platform.agents.models import SkillDefinition
from democrai.core.platform.utils.runtime_names import validate_qualified_runtime_name


class AgentToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, AgentToolDefinition] = {}

    def register(
        self,
        name: str,
        func: Callable[..., Any],
        *,
        description: str = "",
        input_schema: dict[str, Any] | None = None,
        title: str = "",
        module_name: str = "core",
        confirmation_required: bool = False,
        access: list[AccessManifestRule] | None = None,
        user_selectable: bool = True,
    ) -> None:
        resolved_name = validate_qualified_runtime_name(name, kind="tool name")
        resolved_description = description if isinstance(description, str) else ""
        resolved_title = title if isinstance(title, str) else ""
        resolved_module_name = (
            module_name.strip()
            if isinstance(module_name, str) and module_name.strip()
            else "core"
        )
        self._tools[resolved_name] = AgentToolDefinition(
            name=resolved_name,
            func=func,
            description=resolved_description,
            input_schema=(
                {"type": "object", "properties": {}}
                if input_schema is None
                else input_schema
            ),
            title=resolved_title,
            module_name=resolved_module_name,
            confirmation_required=bool(confirmation_required),
            access=access if access is not None else [],
            user_selectable=bool(user_selectable),
        )

    def get(self, name: str) -> AgentToolDefinition | None:
        _ensure_builtin_tools_loaded()
        return self._tools.get(name)

    def get_all(self, *, module_name: str | None = None) -> list[AgentToolDefinition]:
        _ensure_builtin_tools_loaded()
        values = list(self._tools.values())
        if module_name is None:
            return sorted(values, key=lambda item: item.name)
        return sorted(
            [item for item in values if item.module_name == module_name],
            key=lambda item: item.name,
        )


class AgentRegistry:
    def __init__(self) -> None:
        self._agents: dict[str, AgentDefinition] = {}

    def register(self, definition: AgentDefinition) -> None:
        validate_qualified_runtime_name(definition.name, kind="agent name")
        self._agents[definition.name] = definition

    def get(self, name: str) -> AgentDefinition | None:
        return self._agents.get(name)

    def get_all(self, *, module_name: str | None = None) -> list[AgentDefinition]:
        values = list(self._agents.values())
        if module_name is None:
            return sorted(values, key=lambda item: item.name)
        return sorted(
            [item for item in values if item.module_name == module_name],
            key=lambda item: item.name,
        )


class PipelineRegistry:
    def __init__(self) -> None:
        self._pipelines: dict[str, PipelineDefinition] = {}

    def register(self, definition: PipelineDefinition) -> None:
        self._pipelines[definition.name] = definition

    def get(self, name: str) -> PipelineDefinition | None:
        return self._pipelines.get(name)

    def get_all(self, *, module_name: str | None = None) -> list[PipelineDefinition]:
        values = list(self._pipelines.values())
        if module_name is None:
            return sorted(values, key=lambda item: item.name)
        return sorted(
            [item for item in values if item.module_name == module_name],
            key=lambda item: item.name,
        )


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: dict[str, SkillDefinition] = {}

    def register(self, definition: SkillDefinition) -> None:
        self._skills[definition.metadata.name] = definition

    def get(self, name: str) -> SkillDefinition | None:
        return self._skills.get(name)

    def get_all(self, *, module_name: str | None = None) -> list[SkillDefinition]:
        values = list(self._skills.values())
        if module_name is None:
            return sorted(values, key=lambda item: item.metadata.name)
        return sorted(
            [
                item
                for item in values
                if item.metadata.module_name == module_name
            ],
            key=lambda item: item.metadata.name,
        )


agent_tool_registry = AgentToolRegistry()
agent_registry = AgentRegistry()
pipeline_registry = PipelineRegistry()
skill_registry = SkillRegistry()

_BUILTIN_TOOLS_LOADED = False


def _ensure_builtin_tools_loaded() -> None:
    global _BUILTIN_TOOLS_LOADED
    if _BUILTIN_TOOLS_LOADED:
        return
    _BUILTIN_TOOLS_LOADED = True
    importlib.import_module("democrai.core.platform.agents.builtin_tools")
