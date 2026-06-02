from __future__ import annotations

import os
from typing import Any, Optional


def _log_ai_sdk_error(*, generator: str, error: BaseException) -> None:
    try:
        from democrai.core.runtime.foundation.app import app_ctx

        logger = app_ctx().logger
        if logger is None:
            return
        logger.error(
            "[AI Pipeline] sdk ai failed "
            f"generator={generator} error_type={type(error).__name__} error={error}",
            exc_info=True,
        )
    except Exception:
        pass


class AI:
    def __init__(self, sdk) -> None:
        self.sdk = sdk

    def _empty_composer_options(
        self,
        status: str,
        *,
        model_registry_id: int | None = None,
    ) -> dict[str, Any]:
        return {
            "configured": False,
            "status": status,
            "model_registry_id": model_registry_id,
            "model_capabilities": [],
            "options_schema": {"fields": []},
            "options": {},
            "options_editable": False,
        }

    def _composer_reasoning_field(self, model: dict[str, Any]) -> dict[str, Any]:
        capabilities = set(model.get("capabilities") or [])
        if "reasoning" not in capabilities:
            return {}

        features = (model.get("extra_config") or {}).get("features") or {}
        reasoning = features.get("reasoning") or {}
        activation = reasoning.get("activation") or {}
        if not reasoning.get("supported") or activation.get("mode") != "extra_param":
            return {}

        param = activation.get("param")
        if not param:
            return {}

        field_type = activation.get("type") or "boolean"
        field = {
            "name": f"extra.{param}",
            "label": self.sdk.i18n.t("system.capabilities.capability.reasoning"),
            "type": "checkbox" if field_type == "boolean" else field_type,
            "value": activation.get("default"),
        }
        if "values" in activation and field["type"] != "checkbox":
            field["options"] = [
                {"label": value, "value": value} for value in activation["values"]
            ]
        return field

    def _composer_options_from_model(self, model: dict[str, Any]) -> dict[str, Any]:
        reasoning_field = self._composer_reasoning_field(model)
        options_schema = (
            {"fields": [reasoning_field]} if reasoning_field else {"fields": []}
        )
        options = {}
        if reasoning_field:
            options[reasoning_field["name"]] = reasoning_field["value"]

        return {
            "configured": model.get("status") == "active",
            "status": model.get("status") or "missing",
            "model_registry_id": model.get("id"),
            "model_capabilities": model.get("capabilities") or [],
            "options_schema": options_schema,
            "options": options,
            "options_editable": bool(reasoning_field),
        }

    def get_composer_options_by_model_registry_id(
        self,
        model_registry_id: int | str,
    ) -> dict[str, Any]:
        model_id = int(model_registry_id)
        model = self.sdk.models.model_registry.view(model_id)
        if model is None:
            return self._empty_composer_options(
                "model_registry_row_not_found",
                model_registry_id=model_id,
            )
        return self._composer_options_from_model(model)

    def get_composer_options_for_capability(self, capability: str) -> dict[str, Any]:
        priority_rows = self.sdk.models.model_capability_priority.list(
            filters={"capability": capability},
            sort={"field": "priority", "direction": "asc"},
            page=0,
            page_size=200,
        )
        for priority in priority_rows["rows"]:
            options = self.get_composer_options_by_model_registry_id(
                priority["model_id"]
            )
            if options["configured"]:
                return options
        return self._empty_composer_options(
            f"no_active_model_configured_for_capability:{capability}"
        )

    async def get_provider_for_objective(
        self,
        objective: str,
        *,
        required_capabilities: Optional[list[str]] = None,
        prefer_local: Optional[bool] = None,
    ) -> dict[str, Any]:
        if os.environ.get("DEMOCRAI_ENGINE_ORCHESTRATOR") == "1":
            from democrai.core.application.ai.orchestrator import model_orchestrator

            return await model_orchestrator.get_provider_for_objective(
                objective,
                required_capabilities=required_capabilities,
                prefer_local=prefer_local,
            )
        from democrai.core.application.ai.engine.orchestrator.remote_provider import (
            RemoteEngineProvider,
        )

        provider = RemoteEngineProvider(
            selector_type="objective",
            objective=objective,
            capabilities=list(required_capabilities or []),
            prefer_local=prefer_local,
        )
        try:
            validation = await provider.validate()
        except Exception as exc:
            _log_ai_sdk_error(
                generator=f"provider_validation:objective:{objective}",
                error=exc,
            )
            return {"status": "error", "error": str(exc).split("\n", 1)[0]}
        if validation.get("status") not in {"ok", "need_confirmation"}:
            return validation
        return {
            "status": "ok",
            "provider": provider,
            "validation": validation,
        }

    async def get_provider_by_model_registry_id(
        self,
        model_registry_id: int | str,
        *,
        confirm_swap: bool = False,
    ) -> dict[str, Any]:
        if os.environ.get("DEMOCRAI_ENGINE_ORCHESTRATOR") == "1":
            from democrai.core.application.ai.orchestrator import model_orchestrator

            return await model_orchestrator.get_provider_by_model_registry_id(
                model_registry_id,
                confirm_swap=confirm_swap,
            )
        from democrai.core.application.ai.engine.orchestrator.remote_provider import (
            RemoteEngineProvider,
        )

        provider = RemoteEngineProvider(
            selector_type="model_registry_id",
            model_registry_id=int(model_registry_id),
            confirm_swap=confirm_swap,
        )
        try:
            validation = await provider.validate()
        except Exception as exc:
            _log_ai_sdk_error(
                generator=f"provider_validation:model_registry:{model_registry_id}",
                error=exc,
            )
            return {"status": "error", "error": str(exc).split("\n", 1)[0]}
        if validation.get("status") not in {"ok", "need_confirmation"}:
            return validation
        return {
            "status": "ok",
            "provider": provider,
            "validation": validation,
        }

    async def warmup_provider(
        self, provider: Any, *, wait: bool = True
    ) -> dict[str, Any]:
        warmup = getattr(provider, "warmup", None)
        if not callable(warmup):
            return {"status": "error", "error": "provider_warmup_unavailable"}
        result = await warmup(wait=wait)
        return dict(result or {})

    def cancel_request(self, request_id: str) -> bool:
        from democrai.core.application.ai.engine.runtime.requests import (
            cancel_runtime_request,
        )

        return cancel_runtime_request(request_id)

    def list_tools(
        self,
        module_name: Optional[str] = None,
        *,
        user_selectable_only: bool = True,
    ):
        from democrai.core.platform.agents.registry import agent_tool_registry

        tools = agent_tool_registry.get_all(module_name=module_name)
        if user_selectable_only:
            return [tool for tool in tools if tool.user_selectable]
        return tools

    def get_tool(self, name: str):
        from democrai.core.platform.agents.registry import agent_tool_registry

        return agent_tool_registry.get(name)

    def list_agents(self, module_name: Optional[str] = None):
        from democrai.core.platform.agents.registry import agent_registry

        return agent_registry.get_all(module_name=module_name)

    def get_agent(self, name: str):
        from democrai.core.platform.agents.registry import agent_registry

        return agent_registry.get(name)

    def list_mcp_servers(self):
        from democrai.core.platform.mcp.registry import list_servers

        return list_servers(enabled_only=True)

    def list_pipelines(self, module_name: Optional[str] = None):
        from democrai.core.platform.agents.registry import pipeline_registry

        return pipeline_registry.get_all(module_name=module_name)

    def get_pipeline(self, name: str):
        from democrai.core.platform.agents.registry import pipeline_registry

        return pipeline_registry.get(name)

    def list_skills(
        self,
        allowed_names: Optional[list[str]] = None,
        module_name: Optional[str] = None,
    ):
        from democrai.core.platform.agents.registry import skill_registry

        skills = skill_registry.get_all(module_name=module_name)
        allowed = {
            str(name or "").strip().lower()
            for name in (allowed_names or [])
            if str(name or "").strip()
        }
        return [
            skill
            for skill in skills
            if not allowed or skill.metadata.name.lower() in allowed
        ]

    async def run_tool(
        self,
        name: str,
        *,
        arguments: Optional[dict[str, Any]] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> Any:
        from democrai.core.platform.agents.runtime import agent_runtime
        from democrai.core.platform.agents.registry import agent_tool_registry

        tool_def = agent_tool_registry.get(name)
        if not tool_def:
            raise ValueError(f"Tool not found: {name}")

        async def _run():
            return await agent_runtime.run_tool(
                name,
                arguments=arguments,
                context=context,
            )

        return await _run()

    async def run_agent(
        self,
        name: str,
        *,
        input: str = "",
        context: Optional[dict[str, Any]] = None,
        extra_tools: Optional[list[str] | tuple[str, ...]] = None,
        extra_skills: Optional[list[str] | tuple[str, ...]] = None,
        extra_mcp_servers: Optional[list[str] | tuple[str, ...]] = None,
        extra_agents: Optional[list[str] | tuple[str, ...]] = None,
        max_iterations: Optional[int] = None,
        model_registry_id: Optional[int | str] = None,
        listener: Any = None,
        on_message: Any = None,
    ):
        from democrai.core.platform.agents.runtime import agent_runtime
        from democrai.core.platform.agents.registry import agent_registry

        agent_def = agent_registry.get(name)
        if not agent_def:
            raise ValueError(f"Agent not found: {name}")

        async def _run():
            provider = None
            if model_registry_id not in (None, ""):
                provider_result = await self.get_provider_by_model_registry_id(
                    model_registry_id
                )
                if provider_result.get("status") != "ok" or not provider_result.get(
                    "provider"
                ):
                    raise RuntimeError(
                        provider_result.get("error") or "provider_unavailable"
                    )
                provider = provider_result["provider"]
            return await agent_runtime.run_agent(
                name,
                input=input,
                context=context,
                provider_override=provider,
                extra_tools=extra_tools,
                extra_skills=extra_skills,
                extra_mcp_servers=extra_mcp_servers,
                extra_agents=extra_agents,
                max_iterations=max_iterations,
                listener=listener,
                on_message=on_message,
            )

        return await _run()

    async def run_pipeline(
        self,
        name: str,
        *,
        input: str = "",
        context: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        from democrai.core.platform.agents.runtime import agent_runtime
        from democrai.core.platform.agents.registry import pipeline_registry

        pipeline_def = pipeline_registry.get(name)
        if not pipeline_def:
            raise ValueError(f"Pipeline not found: {name}")

        async def _run():
            return await agent_runtime.run_pipeline(
                name,
                input=input,
                context=context,
            )

        return await _run()
