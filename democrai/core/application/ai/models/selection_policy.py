from __future__ import annotations

from typing import Any, Optional

from democrai.core.application.ai.constants import (
    AIDeployment,
    normalize_capabilities,
    normalize_token,
)
from democrai.core.application.ai.engine.manifests import get_provider_definition


def _provider_deployment(provider_name: str) -> str:
    definition = get_provider_definition(provider_name) or {}
    return normalize_token(definition.get("deployment"))


def annotate_provider(provider: Any, *, model_info: Any, engine_name: str | None = None) -> Any:
    if provider is None:
        return provider
    resolved_engine = engine_name or str(getattr(model_info, "provider", "") or "")
    deployment_mode = _provider_deployment(getattr(model_info, "provider", ""))
    if deployment_mode not in {AIDeployment.LOCAL, AIDeployment.HYBRID, AIDeployment.REMOTE}:
        deployment_mode = "unknown"
    for target in (provider, getattr(provider, "real_provider", None)):
        if target is None:
            continue
        try:
            setattr(target, "_democrai_provider_name", str(getattr(model_info, "provider", "") or ""))
            setattr(target, "_democrai_engine_name", resolved_engine)
            setattr(target, "_democrai_model_name", str(getattr(model_info, "name", "") or getattr(target, "model_name", "") or ""))
            setattr(target, "_democrai_deployment_mode", deployment_mode)
        except Exception:
            continue
    return provider


def provider_capabilities(model: Any) -> set[str]:
    raw = getattr(model, "capabilities", "") or ""
    return set(normalize_capabilities(raw))


def is_local_provider(provider: str) -> bool:
    return _provider_deployment(provider) == "local"


def effective_policy_mode(policy: dict[str, Any], *, objective: str, prefer_local: Optional[bool]) -> str:
    if prefer_local is True:
        return "local"
    if prefer_local is False:
        return "cloud"
    overrides = policy.get("objective_overrides") if isinstance(policy.get("objective_overrides"), dict) else {}
    objective_policy = overrides.get(objective) if isinstance(overrides.get(objective), dict) else {}
    mode = objective_policy.get("deployment") or policy.get("default_deployment") or "hybrid"
    return mode


def engine_fit_score(provider: str, required_capabilities: set[str], *, hardware_validator: Any) -> int:
    preferred = hardware_validator.recommend_local_llm_engines(required_capabilities=sorted(required_capabilities))
    if provider in preferred:
        return 40 - (preferred.index(provider) * 8)
    deployment = _provider_deployment(provider)
    if deployment == AIDeployment.REMOTE:
        return 16
    if deployment == AIDeployment.HYBRID:
        return 8
    return 0
