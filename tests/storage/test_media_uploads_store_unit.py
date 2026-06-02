from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import democrai.core.infrastructure.database.media_uploads as store_mod
from democrai.core.infrastructure.database.models import Base


def test_media_uploads_store_create_and_get(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def session_scope():
        session = SessionLocal()
        if hasattr(session, "__enter__") and hasattr(session, "__exit__"):
            return session

    Base.metadata.create_all(engine)
    monkeypatch.setattr(store_mod, "session_scope", session_scope)

    store_mod.create_media_upload(
        file_id="f1",
        module_name="knowledge",
        storage_path="media/knowledge/uid_1/2026/03/05/f1_doc.txt",
        original_filename="doc.txt",
        stored_filename="f1_doc.txt",
        content_type="text/plain",
        size_bytes=10,
        sha256="abc",
        scope_type="user",
        owner_user_id=1,
        organization_id=None,
        uploaded_by=1,
        uploader_access_level=3,
    )
    row = store_mod.get_media_upload_by_file_id(file_id="f1")
    assert row is not None
    assert row.module_name == "knowledge"
    assert row.storage_path.endswith("f1_doc.txt")


def test_media_uploads_store_list_filters_and_pagination(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def session_scope():
        session = SessionLocal()
        if hasattr(session, "__enter__") and hasattr(session, "__exit__"):
            return session

    Base.metadata.create_all(engine)
    monkeypatch.setattr(store_mod, "session_scope", session_scope)

    base_time = datetime(2026, 3, 5, 12, 0, 0)
    with session_scope() as session:
        session.add_all(
            [
                store_mod.MediaUpload(
                    file_id="f1",
                    module_name="knowledge",
                    storage_path="media/knowledge/uid_1/2026/03/05/f1_doc.txt",
                    original_filename="doc.txt",
                    stored_filename="f1_doc.txt",
                    content_type="text/plain",
                    size_bytes=1,
                    sha256="a",
                    scope_type="user",
                    owner_user_id=1,
                    organization_id=None,
                    uploaded_by=1,
                    uploader_access_level=3,
                    created_at=base_time,
                ),
                store_mod.MediaUpload(
                    file_id="f2",
                    module_name="knowledge",
                    storage_path="media/knowledge/org_10/uid_2/2026/03/05/f2_doc.txt",
                    original_filename="doc2.txt",
                    stored_filename="f2_doc.txt",
                    content_type="text/plain",
                    size_bytes=1,
                    sha256="b",
                    scope_type="organization",
                    owner_user_id=2,
                    organization_id=10,
                    uploaded_by=2,
                    uploader_access_level=2,
                    created_at=base_time + timedelta(minutes=1),
                ),
            ]
        )
        session.commit()

    rows, total = store_mod.list_media_uploads(
        module_name="knowledge", page=1, page_size=1
    )
    assert total == 2
    assert len(rows) == 1
    assert rows[0].file_id == "f2"

    rows, total = store_mod.list_media_uploads(
        organization_id=10,
        scope_type="organization",
        created_from=base_time,
        created_to=base_time + timedelta(minutes=2),
    )
    assert total == 1
    assert rows[0].file_id == "f2"


def test_media_uploads_store_storage_path_and_owner_filter(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def session_scope():
        session = SessionLocal()
        if hasattr(session, "__enter__") and hasattr(session, "__exit__"):
            return session

    Base.metadata.create_all(engine)
    monkeypatch.setattr(store_mod, "session_scope", session_scope)

    store_mod.create_media_upload(
        file_id="f-owner",
        module_name="knowledge",
        storage_path="media/knowledge/uid_9/2026/03/05/f-owner_doc.txt",
        original_filename="doc.txt",
        stored_filename="f-owner_doc.txt",
        content_type="text/plain",
        size_bytes=10,
        sha256="xyz",
        scope_type="user",
        owner_user_id=9,
        organization_id=None,
        uploaded_by=9,
        uploader_access_level=3,
    )

    by_path = store_mod.get_media_upload_by_storage_path(
        storage_path="media/knowledge/uid_9/2026/03/05/f-owner_doc.txt"
    )
    assert by_path is not None
    assert by_path.file_id == "f-owner"

    rows, total = store_mod.list_media_uploads(owner_user_id=9)
    assert total == 1
    assert rows[0].file_id == "f-owner"
