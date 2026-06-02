from __future__ import annotations

import pytest
from fastapi import HTTPException

from democrai.core.application.handler.services.runtime import media_proxy as proxy_mod
from democrai.core.application.handler.services.runtime.media_targets import (
    parse_media_proxy_target,
)
from democrai.core.runtime.foundation.app import RequestContext, reset_req_ctx, set_req_ctx


def test_parse_media_proxy_target_remote():
    target = parse_media_proxy_target(module_name="chat", url="https://example.com/a.png")

    assert target.kind == "remote"
    assert target.requester_module == "chat"
    assert target.remote_url == "https://example.com/a.png"


def test_parse_media_proxy_target_internal_assets():
    module_target = parse_media_proxy_target(
        module_name="chat",
        url="/media/modules/dashboard/assets/logo.svg",
    )
    assert module_target.kind == "module_asset"
    assert module_target.owner_name == "dashboard"
    assert module_target.relative_path == "assets/logo.svg"

    engine_target = parse_media_proxy_target(
        module_name="chat",
        url="/media/engine/openai/assets/icon.svg",
    )
    assert engine_target.kind == "engine_asset"
    assert engine_target.owner_name == "openai"
    assert engine_target.relative_path == "assets/icon.svg"

    extractor_target = parse_media_proxy_target(
        module_name="chat",
        url="/media/extractors/docling/assets/icon.svg",
    )
    assert extractor_target.kind == "extractor_asset"
    assert extractor_target.owner_name == "docling"
    assert extractor_target.relative_path == "assets/icon.svg"


def test_parse_media_proxy_target_uploads():
    file_target = parse_media_proxy_target(
        module_name="chat",
        url="/media/uploads/file-1",
    )
    assert file_target.kind == "upload_file_id"
    assert file_target.file_id == "file-1"

    storage_target = parse_media_proxy_target(
        module_name="chat",
        url="/media/uploads/by-storage-path?storage_path=media%2Fx.png",
    )
    assert storage_target.kind == "upload_storage_path"
    assert storage_target.storage_path == "media/x.png"


@pytest.mark.parametrize(
    ("module_name", "url"),
    [
        ("", "https://example.com/a.png"),
        ("chat", ""),
        ("chat", "ftp://example.com/a.png"),
        ("chat", "/media/uploads/"),
        ("chat", "/media/uploads/by-storage-path"),
        ("chat", "/media/modules/dashboard"),
        ("chat", "/media/modules/dashboard/../secret.png"),
        ("chat", "/media/engine/openai"),
        ("chat", "/media/extractors/docling"),
    ],
)
def test_parse_media_proxy_target_rejects_invalid_targets(module_name, url):
    with pytest.raises(HTTPException) as exc:
        parse_media_proxy_target(module_name=module_name, url=url)

    assert exc.value.status_code in {400, 404}


@pytest.mark.asyncio
async def test_proxy_external_media_dispatches_internal_target(monkeypatch):
    calls = []

    async def serve_media_target_stub(target, **_kwargs):
        calls.append(target)
        return {"served": "engine_asset"}

    monkeypatch.setattr(
        proxy_mod,
        "serve_media_target",
        serve_media_target_stub,
    )

    request = object()

    token = set_req_ctx(
        RequestContext(
            app=None,
            request_id="r",
            user=1,
            role="User",
            organization_id=2,
            access_level=2,
            channel="http",
            session_key="s1",
        )
    )
    try:
        internal = await proxy_mod.proxy_external_media(
            "chat",
            "/media/engine/openai/assets/icon.svg",
            request,
        )
    finally:
        reset_req_ctx(token)

    assert internal == {"served": "engine_asset"}
    assert calls[0].kind == "engine_asset"
    assert calls[0].owner_name == "openai"
    assert calls[0].relative_path == "assets/icon.svg"
