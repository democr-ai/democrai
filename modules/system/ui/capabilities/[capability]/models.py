from __future__ import annotations

from urllib.parse import unquote

from democrai.sdk.client import active_sdk as sdk

from modules.system.utils.actions.capabilities.index import capability_priority_form_data
from modules.system.utils.ui.capabilities.list import build_capability_tab


async def render(params: dict, session: dict):
    route_params = dict(params.get("route_params") or {})
    capability = unquote(str(route_params.get("capability") or "")).strip().lower()

    builder = sdk.ui.Builder()
    form_data = capability_priority_form_data(sdk, capability)
    build_capability_tab(builder, sdk, capability, form_data)
    return builder
