from __future__ import annotations

from democrai.sdk.client import active_sdk as sdk


async def render(_params: dict, _session: dict):
    return sdk.ui.load("utils/ui/yaml/profile_password")
