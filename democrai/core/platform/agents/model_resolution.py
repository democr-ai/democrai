from __future__ import annotations

from democrai.core.application.ai.pipeline_context import current_ai_pipeline_context
from democrai.core.infrastructure.database import SessionLocal
from democrai.core.infrastructure.database.models import AgentModelConfig, ModelRegistry
from democrai.core.platform.agents.models import AgentDefinition


def _active_chat_or_tool_model(session, model_id: int | None) -> bool:
    if model_id is None:
        return False
    row = session.query(ModelRegistry).filter(ModelRegistry.id == int(model_id)).first()
    status = row.status.strip().lower() if row is not None and isinstance(row.status, str) else ""
    if row is None or status != "active":
        return False
    raw_capabilities = row.capabilities if isinstance(row.capabilities, str) else ""
    capabilities = {item.strip() for item in raw_capabilities.split(",")}
    return bool({"chat", "tool_calling"} & capabilities)


async def resolve_agent_provider(definition: AgentDefinition, parent_provider=None):
    from democrai.core.application.ai.orchestrator import model_orchestrator

    async def by_system():
        result = await model_orchestrator.get_provider_for_objective(definition.objective)
        if result.get("status") != "ok" or "provider" not in result:
            raise RuntimeError(result.get("error") or f"Provider unavailable for objective '{definition.objective}'")
        return result["provider"]

    with SessionLocal() as session:
        config = session.query(AgentModelConfig).filter(AgentModelConfig.agent_name == definition.name).first()
        policy = (
            config.model_policy.strip()
            if config is not None
            and isinstance(config.model_policy, str)
            and config.model_policy.strip()
            else "by_system"
        )
        configured_model_id = int(config.model_registry_id) if config is not None and config.model_registry_id is not None else None
        context = current_ai_pipeline_context()
        parent_model_id = context.model_registry_id if context is not None else None
        if policy == "by_parent" and parent_provider is not None:
            return parent_provider
        model_id = parent_model_id if policy == "by_parent" else configured_model_id if policy == "specific_model" else None
        if policy in {"by_parent", "specific_model"} and _active_chat_or_tool_model(session, model_id):
            result = await model_orchestrator.get_provider_by_model_registry_id(model_id)
            if result.get("status") == "ok" and "provider" in result:
                return result["provider"]
    return await by_system()
