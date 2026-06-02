from __future__ import annotations

from urllib.parse import urljoin, urlparse

import httpx
from fastapi import HTTPException
from fastapi.responses import JSONResponse
from fastapi.responses import StreamingResponse

from democrai.core.application.auth.jwt import session_cookie_name
from democrai.core.application.handler.services.runtime.access import (
    _external_httpx_client_kwargs,
)
from democrai.core.application.handler.services.runtime.media_authorization import (
    authorize_remote_media_request,
)
from democrai.core.application.handler.services.runtime.media_targets import MediaTarget
from democrai.core.platform.utils.debug import debug_media_flow
from democrai.core.runtime.foundation.app import app_ctx, req_ctx


MAX_REDIRECT_HOPS = 8
FORWARDED_PROXY_REQUEST_HEADERS = {"range", "if-range", "accept", "user-agent"}
FORWARDED_PROXY_RESPONSE_HEADERS = {
    "accept-ranges",
    "cache-control",
    "content-length",
    "content-range",
    "content-type",
    "etag",
    "last-modified",
}


def debug_remote_media(message: str) -> None:
    logger = getattr(app_ctx(), "logger", None)
    if logger is not None:
        logger.debug(message)


def resolve_redirect_url(current_url: str, location: str) -> str:
    next_url = urljoin(current_url, location.strip())
    parsed = urlparse(next_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(
            status_code=502, detail="Invalid upstream redirect location"
        )
    return next_url


async def proxy_remote_media(target: MediaTarget, request):
    ctx = req_ctx()
    module_name = target.requester_module
    url = target.remote_url
    session_key = (
        str(getattr(request, "cookies", {}).get(session_cookie_name()) or "").strip()
        or ctx.session_key
    )
    debug_media_flow(
        "media_remote.proxy_remote_media.start",
        module_name=module_name,
        url=url,
        user_id=ctx.user,
        organization_id=ctx.organization_id,
        session_key=session_key,
    )
    forwarded_headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() in FORWARDED_PROXY_REQUEST_HEADERS
    }
    client_kwargs = _external_httpx_client_kwargs()
    client_kwargs["follow_redirects"] = False
    debug_media_flow(
        "media_remote.proxy_remote_media.client",
        module_name=module_name,
        url=url,
        trust_env=client_kwargs.get("trust_env", True),
        proxy=client_kwargs.get("proxy"),
    )
    client = httpx.AsyncClient(**client_kwargs)
    access_check = None
    current_url = url
    redirect_hops = 0
    try:
        while True:
            with authorize_remote_media_request(
                target,
                remote_url=current_url,
                session_key=session_key,
            ) as authorization:
                access_check = authorization.external_access
                if not access_check.allowed:
                    code = getattr(access_check, "code", "") or ""
                    message = getattr(access_check, "message", "") or ""
                    debug_media_flow(
                        "media_remote.proxy_remote_media.denied",
                        module_name=module_name,
                        url=current_url,
                        code=code,
                        message=message,
                    )
                    return JSONResponse(
                        status_code=403,
                        content={
                            "error": message,
                            "error_code": code,
                            "module_name": module_name,
                            "url": current_url,
                        },
                        headers={"Content-Type": "application/json"},
                    )
                debug_media_flow(
                    "media_remote.proxy_remote_media.allowed",
                    module_name=module_name,
                    url=current_url,
                    code=getattr(access_check, "code", ""),
                )
                debug_remote_media(
                    f"[media-proxy] allowed module={module_name} url={current_url} code={getattr(access_check, 'code', '')}"
                )

                debug_media_flow(
                    "media_remote.proxy_remote_media.fetch",
                    module_name=module_name,
                    url=current_url,
                )
                debug_remote_media(f"[media-proxy] upstream GET url={current_url}")
                upstream = await client.send(
                    client.build_request("GET", current_url, headers=forwarded_headers),
                    stream=True,
                )
            if 300 <= int(upstream.status_code) < 400:
                location = str(upstream.headers.get("location") or "").strip()
                if not location:
                    await upstream.aclose()
                    raise HTTPException(
                        status_code=502,
                        detail="Upstream redirect missing Location header",
                    )
                next_url = resolve_redirect_url(current_url, location)
                debug_media_flow(
                    "media_remote.proxy_remote_media.redirect",
                    module_name=module_name,
                    from_url=current_url,
                    to_url=next_url,
                    status_code=upstream.status_code,
                )
                debug_remote_media(
                    f"[media-proxy] redirect module={module_name} from={current_url} to={next_url} status={upstream.status_code}"
                )
                await upstream.aclose()
                redirect_hops += 1
                if redirect_hops > MAX_REDIRECT_HOPS:
                    raise HTTPException(
                        status_code=502,
                        detail="Too many upstream redirects",
                    )
                current_url = next_url
                continue
            break
    except httpx.HTTPError as exc:
        debug_remote_media(f"[media-proxy] upstream error={exc}")
        await client.aclose()
        raise HTTPException(
            status_code=502, detail=f"Failed to fetch remote media: {exc}"
        ) from exc
    debug_remote_media(f"[media-proxy] upstream status={upstream.status_code} url={current_url}")
    debug_media_flow(
        "media_remote.proxy_remote_media.response",
        module_name=module_name,
        url=current_url,
        status_code=upstream.status_code,
        content_type=upstream.headers.get("content-type"),
    )

    response_headers = {
        key: value
        for key, value in upstream.headers.items()
        if key.lower() in FORWARDED_PROXY_RESPONSE_HEADERS
    }
    if (getattr(access_check, "code", "") or "") == "session_approval":
        response_headers["cache-control"] = "private, no-store"
        response_headers["pragma"] = "no-cache"
        response_headers["expires"] = "0"

    async def stream_body():
        try:
            async for chunk in upstream.aiter_bytes():
                yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()

    return StreamingResponse(
        stream_body(),
        status_code=upstream.status_code,
        headers=response_headers,
        media_type=upstream.headers.get("content-type"),
    )
