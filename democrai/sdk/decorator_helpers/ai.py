import inspect
from typing import Any, Dict, Optional, cast
from democrai.core.application.access_policy import AccessManifestRule
from democrai.core.platform.agents.models import (
    AgentDefinition,
    PipelineDefinition,
    PipelineStepDefinition,
)
from democrai.core.platform.utils.runtime_names import validate_runtime_name_segment


def tool(
    mod,
    name: Optional[str] = None,
    *,
    title: str = "",
    description: str = "",
    input_schema: Optional[Dict[str, Any]] = None,
    confirmation_required: bool = False,
    access: Optional[list[AccessManifestRule]] = None,
    user_selectable: bool = True,
):
    """Register a callable tool definition for the agent runtime registry."""
    def decorator(func):
        prefix = mod._get_module_prefix(func)
        raw_name = name or func.__name__
        reg_name = (
            f"{prefix}.{raw_name}"
            if prefix and not raw_name.startswith(prefix + ".")
            else raw_name
        )
        mod.agent_tool_registry.register(
            reg_name,
            func,
            title=title,
            description=description or (inspect.getdoc(func) or ""),
            input_schema=input_schema or {"type": "object", "properties": {}},
            module_name=prefix or "core",
            confirmation_required=confirmation_required,
            access=access if access is not None else [],
            user_selectable=user_selectable,
        )
        return func

    return decorator


def agent(
    mod,
    name: Optional[str] = None,
    *,
    title: str = "",
    description: str = "",
    objective: str = "chat",
    system_prompt: str = "",
    tools: Optional[list[str]] = None,
    skills: Optional[list[str]] = None,
    max_iterations: int = 3,
    access: Optional[list[AccessManifestRule]] = None,
    mcp_servers: Optional[list[str]] = None,
    handler: bool = True,
):
    """Register an agent definition backed by a Python handler."""
    def decorator(func):
        prefix = mod._get_module_prefix(func)
        raw_name = name or func.__name__
        reg_name = (
            f"{prefix}.{raw_name}"
            if prefix and not raw_name.startswith(prefix + ".")
            else raw_name
        )

        normalized_mcp_servers: list[str] = []
        seen_mcp: set[str] = set()
        for item in (mcp_servers or []):
            if not isinstance(item, str):
                continue
            candidate = item.strip()
            if not candidate:
                continue
            if candidate == "*":
                raise ValueError(
                    f"agent {reg_name!r}: mcp_servers wildcard '*' is not allowed; "
                    "declare each server explicitly"
                )
            candidate = validate_runtime_name_segment(
                candidate,
                kind=f"agent {reg_name!r} mcp server name",
            )
            if candidate in seen_mcp:
                continue
            seen_mcp.add(candidate)
            normalized_mcp_servers.append(candidate)

        mod.agent_registry.register(
            AgentDefinition(
                name=reg_name,
                title=title,
                description=description or (inspect.getdoc(func) or ""),
                objective=objective,
                system_prompt=system_prompt,
                tools=tuple(
                    item
                    for item in (tools or [])
                    if isinstance(item, str) and item.strip()
                ),
                skills=tuple(
                    item
                    for item in (skills or [])
                    if isinstance(item, str) and item.strip()
                ),
                max_iterations=max(1, int(max_iterations)),
                module_name=prefix or "core",
                handler=func if handler else None,
                access=access if access is not None else [],
                mcp_servers=tuple(normalized_mcp_servers),
            )
        )
        return func

    return decorator


def pipeline(
    mod,
    name: Optional[str] = None,
    *,
    description: str = "",
    steps: Optional[list[PipelineStepDefinition | Dict[str, Any]]] = None,
    access: Optional[list[AccessManifestRule]] = None,
):
    """Register a pipeline definition and normalize dict-based step declarations."""
    def _normalize_step(
        raw_step: PipelineStepDefinition | Dict[str, Any]
    ) -> PipelineStepDefinition:
        if isinstance(raw_step, PipelineStepDefinition):
            return raw_step

        nested_steps: list[PipelineStepDefinition] = []
        raw_nested_steps = raw_step.get("steps")
        if raw_nested_steps is not None:
            if not isinstance(raw_nested_steps, list):
                raise ValueError("pipeline_step_steps_must_be_list")
            for nested in raw_nested_steps:
                if not isinstance(nested, (PipelineStepDefinition, dict)):
                    raise ValueError("pipeline_step_invalid_nested_step")
                nested_steps.append(_normalize_step(nested))

        raw_error_policy = raw_step.get("error_policy", "fail_fast")
        if not isinstance(raw_error_policy, str):
            raise ValueError("pipeline_step_error_policy_must_be_string")
        error_policy = raw_error_policy.strip().lower()
        if error_policy not in {"fail_fast", "collect_errors"}:
            raise ValueError(f"pipeline_step_invalid_error_policy:{error_policy}")
        max_concurrency_raw = raw_step.get("max_concurrency")
        max_concurrency: int | None = None
        if max_concurrency_raw is not None:
            try:
                parsed = int(max_concurrency_raw)
            except (TypeError, ValueError):
                parsed = 0
            if parsed > 0:
                max_concurrency = parsed

        kind = raw_step.get("kind")
        if kind not in {"agent", "tool", "parallel"}:
            raise ValueError(f"pipeline_step_invalid_kind:{kind}")
        target = raw_step.get("target", "")
        if not isinstance(target, str):
            raise ValueError("pipeline_step_target_must_be_string")
        if kind in {"agent", "tool"} and not target:
            raise ValueError(f"pipeline_step_target_required:{kind}")
        output_key = raw_step.get("output_key", "result")
        if not isinstance(output_key, str) or not output_key:
            raise ValueError("pipeline_step_output_key_required")
        raw_arguments = raw_step.get("arguments")
        if raw_arguments is not None and not isinstance(raw_arguments, dict):
            raise ValueError("pipeline_step_arguments_must_be_dict")
        if kind == "parallel" and not nested_steps:
            raise ValueError("pipeline_parallel_step_requires_steps")

        return PipelineStepDefinition(
            kind=kind,
            target=target,
            output_key=output_key,
            input_key=raw_step.get("input_key"),
            input_template=raw_step.get("input_template"),
            arguments=raw_arguments if raw_arguments is not None else {},
            steps=tuple(nested_steps),
            error_policy=error_policy,
            max_concurrency=max_concurrency,
        )

    def decorator(func):
        prefix = mod._get_module_prefix(func)
        raw_name = name or func.__name__
        reg_name = (
            f"{prefix}.{raw_name}"
            if prefix and not raw_name.startswith(prefix + ".")
            else raw_name
        )

        normalized_steps: list[PipelineStepDefinition] = []
        for item in steps or []:
            if not isinstance(item, (PipelineStepDefinition, dict)):
                raise ValueError("pipeline_invalid_step")
            normalized_steps.append(_normalize_step(item))

        mod.pipeline_registry.register(
            PipelineDefinition(
                name=reg_name,
                description=description or (inspect.getdoc(func) or ""),
                steps=tuple(normalized_steps),
                module_name=prefix or "core",
                access=access if access is not None else [],
            )
        )
        return func

    return decorator
