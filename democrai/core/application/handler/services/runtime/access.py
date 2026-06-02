from __future__ import annotations

import base64
import os
from pathlib import Path
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException
from democrai.core.application.auth.service import is_valid_module_name
from democrai.core.application.access_policy import AccessManifestRule
from democrai.core.application.access_policy import AccessResource
from democrai.core.application.access_policy import AccessSubject
from democrai.core.infrastructure.network.policy_guard import network_policy_context
from democrai.core.application.services.external_access import (
    EXTERNAL_RESOURCE_NETWORK,
    check_external_access,
)
from democrai.core.platform.utils.debug import debug_media_flow
from democrai.core.platform.utils.mime_detection import detect_mime_type, filename_hint_from_url
from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.infrastructure.sandbox.proxy_access import is_module_target_declared
from democrai.core.application.handler.services.runtime.cache import (
    cached_media_payload,
    media_cache_path,
    media_cache_ttl_seconds,
    prune_media_cache,
    read_media_cache_metadata,
    write_media_cache_metadata,
)

def _debug(message: str) -> None:
    logger = getattr(app_ctx(), "logger", None)
    if logger is not None:
        logger.debug(message)


def _external_httpx_client_kwargs() -> dict[str, object]:
    kwargs: dict[str, object] = {
        "follow_redirects": True,
        "timeout": httpx.Timeout(30.0, connect=10.0),
    }
    debug_media_flow(
        "runtime_access.httpx_client_kwargs",
        trust_env=kwargs.get("trust_env", True),
        proxy=kwargs.get("proxy"),
        http_proxy_env=str(os.environ.get("HTTP_PROXY") or "").strip(),
        https_proxy_env=str(os.environ.get("HTTPS_PROXY") or "").strip(),
        all_proxy_env=str(os.environ.get("ALL_PROXY") or "").strip(),
    )
    return kwargs


def external_media_fetch_access(
    *,
    module_name: str,
    url: str,
) -> tuple[AccessManifestRule, ...]:
    subject = AccessSubject.create("module", module_name)
    return (
        AccessManifestRule(
            subject=subject,
            resource=AccessResource.create(
                resource_type="network",
                operation="receive",
                target=url,
            ),
        ),
        AccessManifestRule(
            subject=subject,
            resource=AccessResource.create(
                resource_type="network",
                operation="connect",
                target=url,
            ),
        ),
    )

def validate_proxy_request(module_name: str, url: str) -> None:
    raw = url
    if raw.startswith("/media/"):
        if not is_valid_module_name(module_name):
            raise HTTPException(status_code=400, detail="Invalid module name")
        if app_ctx().modules.get_module(module_name) is None:
            raise HTTPException(status_code=404, detail="Module not found")
        return
    parsed = urlparse(url)
    if not is_valid_module_name(module_name):
        raise HTTPException(status_code=400, detail="Invalid module name")
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=400, detail="Invalid media URL")
    if app_ctx().modules.get_module(module_name) is None:
        raise HTTPException(status_code=404, detail="Module not found")
    if not is_module_target_declared(module_name, url, operation="receive"):
        raise HTTPException(status_code=403, detail=f"External URL is locked: {url}")


def validate_proxy_request_structure(module_name: str, url: str) -> None:
    raw = url
    if raw.startswith("/media/"):
        if not is_valid_module_name(module_name):
            raise HTTPException(status_code=400, detail="Invalid module name")
        if app_ctx().modules.get_module(module_name) is None:
            raise HTTPException(status_code=404, detail="Module not found")
        return
    parsed = urlparse(url)
    if not is_valid_module_name(module_name):
        raise HTTPException(status_code=400, detail="Invalid module name")
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=400, detail="Invalid media URL")
    if app_ctx().modules.get_module(module_name) is None:
        raise HTTPException(status_code=404, detail="Module not found")


def check_external_media_access(
    *,
    module_name: str,
    url: str,
    user_id: int | None,
    organization_id: int | None,
    session_key: str | None = None,
    role: str | None = None,
    access_level: int | None = None,
    permissions: list[str] | None = None,
):
    validate_proxy_request_structure(module_name, url)
    debug_media_flow(
        "runtime_access.check_external_media_access",
        module_name=module_name,
        url=url,
        user_id=user_id,
        organization_id=organization_id,
        session_key=session_key,
    )
    return check_external_access(
        subject_type="module",
        subject_name=module_name,
        resource_type=EXTERNAL_RESOURCE_NETWORK,
        operation="receive",
        target=url,
        register_request=True,
    )


async def resolve_external_media_to_cache(
    module_name: str,
    url: str,
    *,
    force_refresh: bool = False,
    skip_allowlist_check: bool = False,
    user_id: int | None = None,
    organization_id: int | None = None,
    session_key: str | None = None,
) -> dict[str, str]:
    debug_media_flow(
        "runtime_access.resolve_external_media_to_cache.start",
        module_name=module_name,
        url=url,
        force_refresh=force_refresh,
        skip_allowlist_check=skip_allowlist_check,
        user_id=user_id,
        organization_id=organization_id,
        session_key=session_key,
    )
    _debug(
        f"[media-cache] start module={module_name} url={url} force_refresh={force_refresh}"
    )
    if skip_allowlist_check:
        validate_proxy_request_structure(module_name, url)
    else:
        validate_proxy_request(module_name, url)
    ttl_seconds = media_cache_ttl_seconds()
    prune_media_cache(module_name, ttl_seconds)
    if not force_refresh:
        cached = cached_media_payload(
            module_name, url, ttl_seconds=ttl_seconds
        )
        if cached is not None:
            debug_media_flow(
                "runtime_access.resolve_external_media_to_cache.cache_hit",
                module_name=module_name,
                url=url,
                path=cached.get("path"),
            )
            _debug(f"[media-cache] cache-hit module={module_name} url={url}")
            return cached

    client = httpx.AsyncClient(**_external_httpx_client_kwargs())
    try:
        debug_media_flow(
            "runtime_access.resolve_external_media_to_cache.fetch",
            module_name=module_name,
            url=url,
        )
        _debug(f"[media-cache] upstream GET url={url}")
        with network_policy_context(
            subject_name=module_name,
            access=external_media_fetch_access(module_name=module_name, url=url),
            user_id=user_id,
            organization_id=organization_id,
            session_key=session_key,
        ):
            response = await client.get(url)
        response.raise_for_status()
        _debug(f"[media-cache] upstream status={response.status_code} url={url}")
        declared_content_type = response.headers.get("content-type")
        detected = detect_mime_type(
            data=response.content,
            filename=filename_hint_from_url(url),
            declared_content_type=declared_content_type,
        )
        declared_normalized = (
            str(declared_content_type or "").split(";", 1)[0].strip().lower()
        )
        content_type = detected.mime_type
        filename_hint = filename_hint_from_url(url)
        if (
            declared_normalized
            and declared_normalized not in {"text/plain", "application/octet-stream"}
            and content_type in {"text/plain", "application/octet-stream"}
        ):
            content_type = declared_normalized
        elif (
            not declared_normalized
            and content_type == "text/plain"
            and not Path(filename_hint).suffix
        ):
            content_type = "application/octet-stream"
        cache_path = media_cache_path(module_name, url, content_type)
        previous = read_media_cache_metadata(module_name, url) or {}
        previous_path = str(previous.get("path") or "")
        cache_path.write_bytes(response.content)
        if previous_path and previous_path != str(cache_path):
            try:
                Path(previous_path).unlink()
            except FileNotFoundError:
                pass
        expires_at = cache_path.stat().st_mtime + float(ttl_seconds)
        payload = {
            "path": str(cache_path),
            "content_type": content_type or "application/octet-stream",
            "url": url,
            "module_name": module_name,
            "cache_hit": "false",
            "cache_expires_at": str(int(expires_at)),
        }
        debug_media_flow(
            "runtime_access.resolve_external_media_to_cache.stored",
            module_name=module_name,
            url=url,
            path=str(cache_path),
            content_type=payload["content_type"],
        )
        write_media_cache_metadata(
            module_name,
            url,
            {
                "path": str(cache_path),
                "content_type": payload["content_type"],
                "url": url,
                "module_name": module_name,
                "cached_at": int(cache_path.stat().st_mtime),
                "expires_at": int(expires_at),
            },
        )
        return payload
    finally:
        await client.aclose()


async def open_external_media_stream(
    module_name: str,
    url: str,
    *,
    forwarded_headers: dict[str, str] | None = None,
    skip_allowlist_check: bool = False,
    user_id: int | None = None,
    organization_id: int | None = None,
    session_key: str | None = None,
) -> tuple[httpx.AsyncClient, httpx.Response, dict[str, str]]:
    debug_media_flow(
        "runtime_access.open_external_media_stream.start",
        module_name=module_name,
        url=url,
        skip_allowlist_check=skip_allowlist_check,
        user_id=user_id,
        organization_id=organization_id,
        session_key=session_key,
    )
    _debug(f"[media-stream] start module={module_name} url={url}")
    if skip_allowlist_check:
        validate_proxy_request_structure(module_name, url)
    else:
        validate_proxy_request(module_name, url)
    client = httpx.AsyncClient(**_external_httpx_client_kwargs())
    try:
        request = client.build_request("GET", url, headers=forwarded_headers or {})
        debug_media_flow(
            "runtime_access.open_external_media_stream.fetch",
            module_name=module_name,
            url=url,
            forwarded_headers=forwarded_headers or {},
        )
        _debug(f"[media-stream] upstream GET url={url}")
        with network_policy_context(
            subject_name=module_name,
            access=external_media_fetch_access(module_name=module_name, url=url),
            user_id=user_id,
            organization_id=organization_id,
            session_key=session_key,
        ):
            response = await client.send(request, stream=True)
        response.raise_for_status()
        _debug(f"[media-stream] upstream status={response.status_code} url={url}")
        debug_media_flow(
            "runtime_access.open_external_media_stream.opened",
            module_name=module_name,
            url=url,
            status_code=response.status_code,
            content_type=response.headers.get("content-type"),
        )
        return (
            client,
            response,
            {
                "content_type": response.headers.get("content-type")
                or "application/octet-stream",
                "content_length": response.headers.get("content-length") or "",
                "url": url,
                "module_name": module_name,
            },
        )
    except Exception as exc:
        _debug(f"[media-stream] upstream error={exc}")
        await client.aclose()
        raise


def encode_media_stream_chunk(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")
