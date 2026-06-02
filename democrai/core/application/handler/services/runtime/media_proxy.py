from __future__ import annotations

from democrai.core.application.handler.services.runtime.media_remote import proxy_remote_media
from democrai.core.application.handler.services.runtime.media_targets import parse_media_proxy_target
from democrai.core.application.handler.services.runtime.media_serving import serve_media_target


async def proxy_external_media(
    module_name: str,
    url: str,
    request,
    *,
    width: int | None = None,
    height: int | None = None,
):
    target = parse_media_proxy_target(module_name=module_name, url=url)
    if target.kind != "remote":
        return await serve_media_target(target, width=width, height=height)

    return await proxy_remote_media(target, request)
