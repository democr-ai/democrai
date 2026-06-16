from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace

import democrai.core.application.services.media_uploads as service_mod
import democrai.core.application.handler.services.runtime.uploads as uploads_mod
import pytest
from fastapi import HTTPException

from democrai.core.application.auth.action import allow_public_upload
from democrai.core.application.auth.action import public
from democrai.core.application.auth.action import setup_only
from democrai.core.application.handler.action_resolution import ResolvedAction
from democrai.core.application.services.media_uploads import MediaUploadResult
from democrai.core.runtime.foundation.app import RequestContext
from democrai.core.runtime.foundation.app import reset_req_ctx
from democrai.core.runtime.foundation.app import set_req_ctx


class _UploadFile:
    filename = "doc.txt"
    content_type = "text/plain"

    def __init__(self):
        self.read_count = 0

    async def read(self):
        self.read_count += 1
        return b"hello"


async def _handler(_ctx, _session, _sdk):
    return {"ok": True}


@public
async def _public_handler(_ctx, _session, _sdk):
    return {"ok": True}


@public
@allow_public_upload
async def _public_upload_handler(_ctx, _session, _sdk):
    return {"ok": True}


@setup_only
async def _setup_only_handler(_ctx, _session, _sdk):
    return {"ok": True}


def _request_ctx(*, user=None, role="user", organization_id=None, access_level=3):
    return RequestContext(
        app=None,
        request_id="req",
        user=user,
        role=role,
        organization_id=organization_id,
        access_level=access_level,
        channel="http",
    )


def _patch_upload_runtime(monkeypatch, *, setup_mode=False):
    monkeypatch.setattr(
        uploads_mod,
        "app_ctx",
        lambda: SimpleNamespace(
            setup_mode=setup_mode,
            logger=SimpleNamespace(warning=lambda *_a: None),
        ),
    )
    monkeypatch.setattr(
        uploads_mod,
        "_core_upload_sdk",
        lambda session: SimpleNamespace(module_name="core"),
    )
    monkeypatch.setattr(uploads_mod, "_get_core_default_actions", lambda: {})
    monkeypatch.setattr(
        "democrai.core.application.auth.module_access.is_module_locked_for_user",
        lambda *args, **kwargs: False,
    )
    monkeypatch.setattr(
        uploads_mod,
        "detect_mime_type",
        lambda **_kwargs: SimpleNamespace(mime_type="text/plain"),
    )
    monkeypatch.setattr(
        uploads_mod,
        "store_uploaded_media",
        lambda **_kwargs: MediaUploadResult(
            file_id="fid",
            storage_path="media/demo/fid_doc.txt",
            stored_filename="fid_doc.txt",
            sha256="sha",
            size_bytes=5,
            scope_type="user",
        ),
    )
    monkeypatch.setattr(
        uploads_mod,
        "get_media_upload_by_file_id",
        lambda **_kwargs: None,
    )


def _set_action(monkeypatch, handler, *, sdk=None):
    resolved_sdk = sdk if sdk is not None else SimpleNamespace(module_name="core")
    monkeypatch.setattr(
        uploads_mod,
        "resolve_core_action",
        lambda action_name, core_actions, sdk: ResolvedAction(
            "core",
            handler,
            resolved_sdk,
        ),
    )
    monkeypatch.setattr(
        uploads_mod,
        "resolve_registry_action",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        uploads_mod,
        "resolve_legacy_action",
        lambda *args, **kwargs: None,
    )


def test_upload_action_public_allows_guest(monkeypatch):
    _patch_upload_runtime(monkeypatch)
    _set_action(monkeypatch, _public_upload_handler)
    token = set_req_ctx(_request_ctx(user=None, role="Guest", access_level=None))
    try:
        file = _UploadFile()
        out = asyncio.run(
            uploads_mod.upload_media_asset(
                module_name="demo",
                file=file,
                ingest=False,
                action_name="demo.public_upload",
            )
        )
    finally:
        reset_req_ctx(token)

    assert file.read_count == 1
    assert out["file_id"] == "fid"


def test_upload_action_public_without_upload_marker_denies_guest(monkeypatch):
    _patch_upload_runtime(monkeypatch)
    _set_action(monkeypatch, _public_handler)
    token = set_req_ctx(_request_ctx(user=None, role="Guest", access_level=None))
    try:
        file = _UploadFile()
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                uploads_mod.upload_media_asset(
                    module_name="demo",
                    file=file,
                    ingest=False,
                    action_name="auth.login_submit",
                )
            )
    finally:
        reset_req_ctx(token)

    assert exc.value.status_code == 403
    assert file.read_count == 0


def test_upload_action_non_public_guest_denied_before_read(monkeypatch):
    _patch_upload_runtime(monkeypatch)
    _set_action(monkeypatch, _handler)
    token = set_req_ctx(_request_ctx(user=None, role="Guest", access_level=None))
    try:
        file = _UploadFile()
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                uploads_mod.upload_media_asset(
                    module_name="demo",
                    file=file,
                    ingest=False,
                    action_name="demo.private_upload",
                )
            )
    finally:
        reset_req_ctx(token)

    assert exc.value.status_code == 401
    assert file.read_count == 0


def test_upload_action_public_permission_denied_before_read(monkeypatch):
    _patch_upload_runtime(monkeypatch)
    _set_action(monkeypatch, _public_upload_handler)
    monkeypatch.setattr(
        uploads_mod,
        "check_action_permissions",
        lambda action_name, handler, permissions: {"error": "permission_denied"},
    )
    token = set_req_ctx(_request_ctx(user=None, role="Guest", access_level=None))
    try:
        file = _UploadFile()
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                uploads_mod.upload_media_asset(
                    module_name="demo",
                    file=file,
                    ingest=False,
                    action_name="demo.public_restricted_upload",
                )
            )
    finally:
        reset_req_ctx(token)

    assert exc.value.status_code == 403
    assert file.read_count == 0


def test_upload_setup_only_action_allows_guest_in_setup_mode(monkeypatch):
    _patch_upload_runtime(monkeypatch, setup_mode=True)
    _set_action(monkeypatch, _setup_only_handler)
    monkeypatch.setattr(
        uploads_mod,
        "check_action_permissions",
        lambda *args, **kwargs: None,
    )
    token = set_req_ctx(_request_ctx(user=None, role="Guest", access_level=None))
    try:
        file = _UploadFile()
        out = asyncio.run(
            uploads_mod.upload_media_asset(
                module_name="demo",
                file=file,
                ingest=False,
                action_name="system.validate_setup_config",
            )
        )
    finally:
        reset_req_ctx(token)

    assert file.read_count == 1
    assert out["file_id"] == "fid"


def test_upload_action_permission_denied_before_read(monkeypatch):
    _patch_upload_runtime(monkeypatch)
    _set_action(monkeypatch, _handler)
    monkeypatch.setattr(uploads_mod, "get_user_permissions", lambda user_id: [])
    monkeypatch.setattr(
        uploads_mod,
        "check_action_permissions",
        lambda action_name, handler, permissions: {"error": "permission_denied"},
    )
    token = set_req_ctx(_request_ctx(user=7))
    try:
        file = _UploadFile()
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                uploads_mod.upload_media_asset(
                    module_name="demo",
                    file=file,
                    ingest=False,
                    action_name="demo.restricted_upload",
                )
            )
    finally:
        reset_req_ctx(token)

    assert exc.value.status_code == 403
    assert file.read_count == 0


def test_upload_action_module_lock_uses_resolved_sdk_module(monkeypatch):
    _patch_upload_runtime(monkeypatch)
    _set_action(
        monkeypatch,
        _handler,
        sdk=SimpleNamespace(module_name="locked_module"),
    )
    monkeypatch.setattr(uploads_mod, "get_user_permissions", lambda user_id: ["p"])
    monkeypatch.setattr(
        uploads_mod,
        "check_action_permissions",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "democrai.core.application.auth.module_access.is_module_locked_for_user",
        lambda module_name, **_kwargs: module_name == "locked_module",
    )
    token = set_req_ctx(_request_ctx(user=7))
    try:
        file = _UploadFile()
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                uploads_mod.upload_media_asset(
                    module_name="demo",
                    file=file,
                    ingest=False,
                    action_name="legacy_upload",
                )
            )
    finally:
        reset_req_ctx(token)

    assert exc.value.status_code == 403
    assert file.read_count == 0


def test_upload_action_permission_allowed(monkeypatch):
    _patch_upload_runtime(monkeypatch)
    _set_action(monkeypatch, _handler)
    monkeypatch.setattr(
        uploads_mod,
        "get_user_permissions",
        lambda user_id: ["demo.upload"],
    )
    monkeypatch.setattr(
        uploads_mod,
        "check_action_permissions",
        lambda *args, **kwargs: None,
    )
    token = set_req_ctx(_request_ctx(user=7))
    try:
        file = _UploadFile()
        out = asyncio.run(
            uploads_mod.upload_media_asset(
                module_name="demo",
                file=file,
                ingest=False,
                action_name="demo.restricted_upload",
            )
        )
    finally:
        reset_req_ctx(token)

    assert file.read_count == 1
    assert out["storage_path"] == "media/demo/fid_doc.txt"


def test_upload_without_action_keeps_authenticated_legacy(monkeypatch):
    _patch_upload_runtime(monkeypatch)
    token = set_req_ctx(_request_ctx(user=7))
    try:
        file = _UploadFile()
        out = asyncio.run(
            uploads_mod.upload_media_asset(
                module_name="demo",
                file=file,
                ingest=False,
            )
        )
    finally:
        reset_req_ctx(token)

    assert file.read_count == 1
    assert out["file_id"] == "fid"


def test_upload_without_action_guest_denied_before_read(monkeypatch):
    _patch_upload_runtime(monkeypatch)
    token = set_req_ctx(_request_ctx(user=None, role="Guest", access_level=None))
    try:
        file = _UploadFile()
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                uploads_mod.upload_media_asset(
                    module_name="demo",
                    file=file,
                    ingest=False,
                )
            )
    finally:
        reset_req_ctx(token)

    assert exc.value.status_code == 401
    assert file.read_count == 0


def test_build_media_upload_path_for_scopes():
    path_super, filename_super, scope_super = service_mod.build_media_upload_path(
        module_name="demo",
        user_id="admin",
        organization_id=None,
        access_level=1,
        original_filename="Report 1.pdf",
        file_id="f123",
        now=datetime(2026, 3, 5),
    )
    assert scope_super == "super"
    assert path_super == "media/demo/uid_admin/2026/03/05/f123_Report_1.pdf"
    assert filename_super == "f123_Report_1.pdf"

    path_org, _, scope_org = service_mod.build_media_upload_path(
        module_name="demo",
        user_id="u1",
        organization_id="acme",
        access_level=2,
        original_filename="invoice.csv",
        file_id="f124",
        now=datetime(2026, 3, 5),
    )
    assert scope_org == "organization"
    assert path_org == "media/demo/org_acme/uid_u1/2026/03/05/f124_invoice.csv"

    path_user, _, scope_user = service_mod.build_media_upload_path(
        module_name="demo",
        user_id="u2",
        organization_id=None,
        access_level=3,
        original_filename="raw name.txt",
        file_id="f125",
        now=datetime(2026, 3, 5),
    )
    assert scope_user == "user"
    assert path_user == "media/demo/uid_u2/2026/03/05/f125_raw_name.txt"


def test_store_uploaded_media_tracks_metadata(monkeypatch):
    saved = []
    created = []
    monkeypatch.setattr(
        service_mod,
        "app_ctx",
        lambda: type(
            "Ctx",
            (),
            {"media": type("Media", (), {"save": staticmethod(lambda path, data: saved.append((path, data)) or path)})()},
        )(),
    )
    monkeypatch.setattr(service_mod, "create_media_upload", lambda **kwargs: created.append(kwargs))
    monkeypatch.setattr(service_mod, "uuid4", lambda: type("U", (), {"hex": "fid"})())

    result = service_mod.store_uploaded_media(
        module_name="knowledge",
        original_filename="Report 1.pdf",
        payload=b"abc",
        content_type="application/pdf",
        user_id="u1",
        organization_id="org-a",
        access_level=2,
        uploaded_by="u1",
    )
    assert result.file_id == "fid"
    assert result.scope_type == "organization"
    assert saved and saved[0][0].startswith("media/knowledge/org_org-a/uid_u1/")
    assert created and created[0]["owner_user_id"] == "u1"
    assert created[0]["organization_id"] == "org-a"
    assert created[0]["size_bytes"] == 3


def test_can_access_media_upload_scope_rules():
    assert service_mod.can_access_media_upload(
        owner_user_id="u1",
        organization_id="org-a",
        user_id="admin",
        user_access_level=1,
        user_organization_id=None,
    )
    assert service_mod.can_access_media_upload(
        owner_user_id="u1",
        organization_id="org-a",
        user_id="u2",
        user_access_level=2,
        user_organization_id="org-a",
    )
    assert not service_mod.can_access_media_upload(
        owner_user_id="u1",
        organization_id="org-a",
        user_id="u2",
        user_access_level=2,
        user_organization_id="org-b",
    )
    assert service_mod.can_access_media_upload(
        owner_user_id="u1",
        organization_id=None,
        user_id="u1",
        user_access_level=3,
        user_organization_id=None,
    )
    assert not service_mod.can_access_media_upload(
        owner_user_id="u1",
        organization_id=None,
        user_id="u2",
        user_access_level=3,
        user_organization_id=None,
    )


def test_media_upload_helpers_cover_invalid_and_empty_paths(monkeypatch):
    assert service_mod.sanitize_upload_filename("") == "file.bin"
    assert service_mod.sanitize_upload_filename("justname") == "justname"
    assert service_mod.sanitize_upload_filename("report.") == "report"

    with pytest.raises(ValueError, match="may not use reserved names|alphanumeric characters"):
        service_mod.build_media_upload_path(
            module_name="../bad",
            user_id="u1",
            organization_id=None,
            access_level=3,
            original_filename="x.txt",
            file_id="f1",
            now=datetime(2026, 3, 5),
        )

    with pytest.raises(ValueError, match="reserved names"):
        service_mod.build_media_upload_path(
            module_name="models",
            user_id="u1",
            organization_id=None,
            access_level=3,
            original_filename="x.txt",
            file_id="f1",
            now=datetime(2026, 3, 5),
        )

    monkeypatch.setattr(service_mod, "app_ctx", lambda: type("Ctx", (), {"media": None})())
    with pytest.raises(RuntimeError, match="Media storage unavailable"):
        service_mod.store_uploaded_media(
            module_name="demo",
            original_filename="a.txt",
            payload=b"x",
            content_type="text/plain",
            user_id="u1",
            organization_id=None,
            access_level=3,
        )

    monkeypatch.setattr(
        service_mod,
        "app_ctx",
        lambda: type("Ctx", (), {"media": type("Media", (), {"save": staticmethod(lambda path, data: path)})()})(),
    )
    with pytest.raises(ValueError, match="Empty payload"):
        service_mod.store_uploaded_media(
            module_name="demo",
            original_filename="a.txt",
            payload=b"",
            content_type="text/plain",
            user_id="u1",
            organization_id=None,
            access_level=3,
        )
