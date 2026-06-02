from __future__ import annotations

from types import SimpleNamespace

import pytest


def test_database_session_scope_covers_context_and_wrapper_paths(monkeypatch):
    mod = __import__("democrai.core.infrastructure.database", fromlist=["dummy"])

    class _SessionCM:
        def __init__(self):
            self.entered = 0
            self.exited = 0
            self.closed = 0

        def __enter__(self):
            self.entered += 1
            return self

        def __exit__(self, exc_type, exc, tb):
            self.exited += 1
            return False

        def close(self):
            self.closed += 1

    cm_session = _SessionCM()
    monkeypatch.setattr(mod, "SessionLocal", lambda: cm_session)
    with mod.session_scope() as session:
        assert session is cm_session
    assert cm_session.entered == 1
    assert cm_session.exited == 1
    assert cm_session.closed == 0

    class _PlainSession:
        def __init__(self):
            self.closed = 0

        def close(self):
            self.closed += 1

    plain_session = _PlainSession()
    monkeypatch.setattr(mod, "SessionLocal", lambda: plain_session)
    with mod.session_scope() as session:
        assert session is plain_session
    assert plain_session.closed == 1

    no_close_session = SimpleNamespace(close=1)
    monkeypatch.setattr(mod, "SessionLocal", lambda: no_close_session)
    scope = mod.session_scope()
    with scope as session:
        assert session is no_close_session
    assert scope.__exit__(None, None, None) is False

    lazy_session = object()
    monkeypatch.setattr(mod, "app_ctx", lambda: SimpleNamespace(db=None))
    monkeypatch.setattr(mod, "_get_lazy_session", lambda: (lambda: lazy_session))
    assert mod.SessionLocalProxy()() is lazy_session


def test_database_get_url_and_lazy_session_additional_branches(monkeypatch):
    mod = __import__("democrai.core.infrastructure.database", fromlist=["dummy"])

    # config exists but has no URL -> fallback path (line 28->32 branch)
    mod._db_url = None
    monkeypatch.setattr(
        mod,
        "app_ctx",
        lambda: SimpleNamespace(config=SimpleNamespace(get=lambda _k: None), db=None),
    )
    monkeypatch.setattr(mod, "get_data_dir", lambda: "/tmp/db-branch")
    assert mod.get_database_url() == "sqlite:////tmp/db-branch/democrai.db"

    # already initialized lazy session path (line 42->52 branch)
    sentinel = object()
    mod._default_SessionLocal = sentinel
    try:
        assert mod._get_lazy_session() is sentinel
    finally:
        mod._default_SessionLocal = None

    # non-sqlite URL path (line 47->49 branch)
    created = {}
    monkeypatch.setattr(mod, "get_database_url", lambda: "postgresql://u:p@localhost/db")
    monkeypatch.setattr(
        mod,
        "create_engine",
        lambda url, connect_args=None: created.setdefault("engine", (url, connect_args)),
    )
    monkeypatch.setattr(mod, "sessionmaker", lambda **kwargs: (lambda: SimpleNamespace()))
    monkeypatch.setattr(mod, "scoped_session", lambda factory: factory)
    mod._default_engine = None
    mod._default_SessionLocal = None
    try:
        assert callable(mod._get_lazy_session())
        assert created["engine"] == ("postgresql://u:p@localhost/db", {})
    finally:
        mod._default_engine = None
        mod._default_SessionLocal = None


def test_database_fallback_is_unavailable_in_setup_mode(monkeypatch):
    mod = __import__("democrai.core.infrastructure.database", fromlist=["dummy"])
    mod._default_engine = None
    mod._default_SessionLocal = None
    monkeypatch.setattr(
        mod,
        "app_ctx",
        lambda: SimpleNamespace(setup_mode=True, db=None, config=None),
    )

    with pytest.raises(RuntimeError, match="database_unavailable_in_setup_mode"):
        mod.SessionLocal()
    assert mod._default_engine is None


def test_database_models_repr_covers_all_model_repr_lines():
    mod = __import__("democrai.core.infrastructure.database.models", fromlist=["dummy"])

    objects = [
        mod.User(username="u1"),
        mod.Role(name="admin"),
        mod.Permission(name="users.read"),
        mod.Organization(name="org"),
        mod.Preference(key="theme", value="dark"),
        mod.ExternalAccessRequest(
            subject_type="module",
            subject_name="m",
            resource_type="network",
            operation="receive",
            target="https://example.com",
            normalized_target="https://example.com",
        ),
        mod.ExternalAccessApproval(
            subject_type="module",
            subject_name="m",
            resource_type="network",
            operation="receive",
            target="https://example.com",
            normalized_target="https://example.com",
        ),
        mod.MediaUpload(
            file_id="f1",
            module_name="m",
            storage_path="/x/f1",
            original_filename="f.txt",
            stored_filename="f1.txt",
            sha256="abc",
            scope_type="user",
            owner_user_id=1,
            uploaded_by=1,
        ),
        mod.EngineRegistry(name="engine", provider="mock"),
        mod.EngineNodeInstallRegistry(engine_id="e1", node_id="n1"),
        mod.ExtractorRegistry(name="ext", extractor_id="ext-1"),
        mod.ExtractorNodeInstallRegistry(extractor_id="ext-1", node_id="n1"),
        mod.ModelRegistry(name="model-1", engine_id=1),
        mod.ObjectiveMapping(objective="chat", model_id=1),
        mod.ModelCapabilityPriority(capability="chat", model_id=1, priority=1),
        mod.Session(user_key="u-key", data="{}"),
        mod.SessionIdentity(session_key="s-key", data="{}"),
        mod.SessionUiState(session_key="s-key", data="{}"),
        mod.ModuleCommandState(module_name="m", command_name="m.cmd", lifecycle="single"),
        mod.ModuleLock(module_name="m"),
    ]

    rendered = [repr(obj) for obj in objects]
    assert len(rendered) == len(objects)
    assert all(isinstance(item, str) and item for item in rendered)
    assert rendered[-1].startswith("<ModuleLock(module_name='m'")
