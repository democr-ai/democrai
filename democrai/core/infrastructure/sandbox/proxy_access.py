from __future__ import annotations

from democrai.core.application.access_policy import AccessOperation
from democrai.core.application.access_policy import ResourceType
from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.infrastructure.network.targets import is_network_target_allowed


def is_module_target_declared(
    module_name: str,
    target: str,
    *,
    operation: str,
) -> bool:
    modules = getattr(app_ctx(), "modules", None)
    if modules is None:
        return False
    module = modules.get_module(module_name)
    if module is None:
        return False
    for rule in module.access:
        if rule.resource.resource_type != ResourceType.NETWORK:
            continue
        if rule.resource.operation != AccessOperation(operation):
            continue
        if is_network_target_allowed(target, [rule.resource.target]):
            return True
    return False
