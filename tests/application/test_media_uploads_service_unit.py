from __future__ import annotations

from datetime import datetime

import democrai.core.application.services.media_uploads as service_mod
import pytest


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
