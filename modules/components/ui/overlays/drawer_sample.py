from __future__ import annotations

from democrai.sdk.auth import permission_required
from democrai.sdk.client import active_sdk as sdk


@permission_required(["components.documentation.view"])
async def render(_params: dict, _session: dict):
    builder = sdk.ui.Builder()
    builder.merge(sdk.ui.load("ui/yaml/overlay_drawer_sample"), components=True)
    return builder
