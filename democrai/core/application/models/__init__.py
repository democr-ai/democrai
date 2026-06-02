from democrai.core.application.models.context import CoreModelContext
from democrai.core.application.models.entities import (
    AgentModelConfigsCoreModel,
    AuditEventsCoreModel,
    AvailableModelRegistryCoreModel,
    BackgroundTasksCoreModel,
    EngineNodeInstallRegistryCoreModel,
    EngineRegistryCoreModel,
    EnvironmentVariableRegistryCoreModel,
    ExtractorMimeTypeBindingCoreModel,
    ExtractorNodeInstallRegistryCoreModel,
    ExtractorRegistryCoreModel,
    AIModelPipelineStepsCoreModel,
    AIModelUsageCoreModel,
    ModelCapabilityPriorityCoreModel,
    ModuleLocksCoreModel,
    McpServerRegistryCoreModel,
    ModelRegistryCoreModel,
    ObjectiveMappingsCoreModel,
    OrganizationAgentsCoreModel,
    OrganizationMcpCoreModel,
    OrganizationToolsCoreModel,
    OrganizationsCoreModel,
    RolesCoreModel,
    UsersCoreModel,
)
from democrai.core.application.models.registry import (
    build_core_model,
    list_core_models,
    register_core_model,
)


register_core_model("background_tasks", lambda ctx: BackgroundTasksCoreModel(ctx))
register_core_model(
    "available_model_registry",
    lambda ctx: AvailableModelRegistryCoreModel(ctx),
)
register_core_model("ai_model_usage", lambda ctx: AIModelUsageCoreModel(ctx))
register_core_model(
    "ai_model_pipeline_steps",
    lambda ctx: AIModelPipelineStepsCoreModel(ctx),
)
register_core_model("audit_events", lambda ctx: AuditEventsCoreModel(ctx))
register_core_model("agent_model_configs", lambda ctx: AgentModelConfigsCoreModel(ctx))
register_core_model("users", lambda ctx: UsersCoreModel(ctx))
register_core_model("roles", lambda ctx: RolesCoreModel(ctx))
register_core_model("organizations", lambda ctx: OrganizationsCoreModel(ctx))
register_core_model("organization_agent", lambda ctx: OrganizationAgentsCoreModel(ctx))
register_core_model("organization_mcp", lambda ctx: OrganizationMcpCoreModel(ctx))
register_core_model("organization_tool", lambda ctx: OrganizationToolsCoreModel(ctx))
register_core_model("module_locks", lambda ctx: ModuleLocksCoreModel(ctx))
register_core_model("engine_registry", lambda ctx: EngineRegistryCoreModel(ctx))
register_core_model(
    "engine_node_install_registry",
    lambda ctx: EngineNodeInstallRegistryCoreModel(ctx),
)
register_core_model(
    "environment_variable_registry",
    lambda ctx: EnvironmentVariableRegistryCoreModel(ctx),
)
register_core_model("extractor_registry", lambda ctx: ExtractorRegistryCoreModel(ctx))
register_core_model(
    "extractor_mime_type_binding",
    lambda ctx: ExtractorMimeTypeBindingCoreModel(ctx),
)
register_core_model(
    "extractor_node_install_registry",
    lambda ctx: ExtractorNodeInstallRegistryCoreModel(ctx),
)
register_core_model("model_registry", lambda ctx: ModelRegistryCoreModel(ctx))
register_core_model("mcp_server_registry", lambda ctx: McpServerRegistryCoreModel(ctx))
register_core_model(
    "model_capability_priority",
    lambda ctx: ModelCapabilityPriorityCoreModel(ctx),
)
register_core_model("objective_mappings", lambda ctx: ObjectiveMappingsCoreModel(ctx))

__all__ = [
    "CoreModelContext",
    "build_core_model",
    "list_core_models",
]
