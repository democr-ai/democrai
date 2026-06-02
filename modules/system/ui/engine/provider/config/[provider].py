from __future__ import annotations

from democrai.sdk.client import active_sdk as sdk
from democrai.sdk.system import to_optional_int

from modules.system.utils.actions.engine.config import (
    default_engine_name,
    provider_display_name,
    render_engine_config_modal,
)


async def render(params: dict, session: dict):
    route_params = dict(params.get("route_params") or {})
    provider = str(route_params.get("provider") or "").strip().lower()
    engine_id = to_optional_int(params.get("engine_id"))
    if not provider:
        return None

    initial_values = {"name": default_engine_name(provider, sdk)}
    if engine_id is not None:
        engine = sdk.models.engine_registry.view(engine_id)
        if isinstance(engine, dict):
            provider = str(engine.get("provider") or provider).strip().lower()
            initial_values = dict(engine.get("config") or {})
            initial_values["name"] = str(
                engine.get("name") or default_engine_name(provider, sdk)
            )

    return render_engine_config_modal(
        sdk,
        provider=provider,
        provider_name=provider_display_name(sdk, provider),
        engine_id=engine_id,
        initial_values=initial_values,
        activate_after_save=engine_id is None,
    )
