from __future__ import annotations

from democrai.sdk.auth import permission_required
from democrai.sdk.decorators import action


@action("media_upload_debug")
@permission_required(["components.documentation.view"])
async def media_upload_debug(ctx: dict, session: dict, sdk) -> dict:
    return {"status": "ok", "context_keys": sorted(str(key) for key in ctx.keys())}
