from __future__ import annotations

import asyncio
import os
import socket
import threading
import urllib.request
from pathlib import Path
from types import SimpleNamespace

import jwt
import pytest
from sqlalchemy import Column, Integer, String, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

import democrai.core.application.auth.jwt as jwt_mod
import democrai.core.application.auth.service as auth_service_mod
from democrai.core.application.auth.roles import ROLE_LEVEL_ORGANIZATION
from democrai.core.application.auth.action import permission_required, public
from democrai.core.application.handler.dispatcher import ActionDispatcher
from democrai.core.application.models.base import BaseCoreModel
from democrai.core.application.models.context import CoreModelContext
from democrai.core.application.request_cycle.engine import RequestCycleEngine
from democrai.core.application.session.service import SessionService
from democrai.core.infrastructure.database.session_store import SessionStore
from democrai.core.infrastructure.database.models import Base as AuthBase
from democrai.core.infrastructure.modules.manager import ModuleManager
from democrai.core.infrastructure.sandbox.process_guard import process_guard_context
from democrai.core.infrastructure.storage.media.providers.local import LocalMediaProvider
from democrai.core.infrastructure.storage.data.store import DataStore
from democrai.core.platform.events import emit_module_event
from democrai.core.runtime.foundation.app import RequestContext, app_ctx, reset_req_ctx, set_req_ctx
from democrai.core.runtime.foundation.registry import module_event_registry


def _silent_logger() -> SimpleNamespace:
    return SimpleNamespace(
        debug=lambda *a, **k: None,
        info=lambda *a, **k: None,
        warning=lambda *a, **k: None,
        error=lambda *a, **k: None,
    )


@pytest.fixture(autouse=True)
def isolated_ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ctx = app_ctx()
    prev_logger = getattr(ctx, "logger", None)
    prev_config = getattr(ctx, "config", None)
    prev_modules = getattr(ctx, "modules", None)
    prev_data_store = getattr(ctx, "data_store", None)
    prev_db = getattr(ctx, "db", None)
    engine = create_engine(f"sqlite:///{tmp_path / 'security-auth.sqlite'}")
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    AuthBase.metadata.create_all(engine)
    monkeypatch.setattr(auth_service_mod, "SessionLocal", SessionLocal)
    ctx.logger = _silent_logger()
    ctx.db = SimpleNamespace(get_session=lambda: SessionLocal())
    try:
        yield ctx
    finally:
        ctx.logger = prev_logger
        ctx.config = prev_config
        ctx.modules = prev_modules
        ctx.data_store = prev_data_store
        ctx.db = prev_db
        engine.dispose()


@pytest.mark.linux_only
def test_security_sandbox_path_traversal_and_symlink_escape_blocked(tmp_path: Path):
    safe = tmp_path / "safe"
    safe.mkdir(parents=True, exist_ok=True)
    (safe / "ok.txt").write_text("ok", encoding="utf-8")

    symlink_out = safe / "out_link"
    symlink_out.symlink_to("/var/lib/democrai_guard_probe_denied")

    with process_guard_context(
        subject="security.sandbox.path",
        allowed_paths=[str(safe)],
        allow_subprocess=False,
    ):
        assert (safe / "ok.txt").read_text(encoding="utf-8") == "ok"

        with pytest.raises(PermissionError):
            Path(
                str(safe / "../../../../../../../../var/lib/democrai_guard_probe_denied")
            ).read_text(
                encoding="utf-8"
            )

        with pytest.raises(PermissionError):
            symlink_out.read_text(encoding="utf-8")


def test_security_sandbox_subprocess_escape_blocked(tmp_path: Path):
    allowed = tmp_path / "allowed"
    allowed.mkdir(parents=True, exist_ok=True)

    with process_guard_context(
        subject="security.sandbox.subprocess",
        allowed_paths=[str(allowed)],
        allow_subprocess=False,
    ):
        with pytest.raises(PermissionError, match="sandbox_"):
            os.system("true")

        with pytest.raises(PermissionError, match="sandbox_"):
            os.popen("echo hi")

        with pytest.raises(PermissionError):
            import ctypes  # noqa: F401


def test_security_auth_rejects_forged_and_expired_jwt(isolated_ctx):
    isolated_ctx.config = SimpleNamespace(
        get=lambda key, default=None: {
            "auth.jwt_secret": "real-secret-for-tests-at-least-32b",
            "auth.jwt_algorithm": "HS256",
            "auth.jwt_issuer": "democrai-test",
            "auth.jwt_audience": None,
            "auth.jwt_tid": None,
        }.get(key, default)
    )

    forged = jwt.encode(
        {"sub": "attacker", "iss": "democrai-test"},
        "different-secret-key-for-tests-32bytes",
        algorithm="HS256",
    )
    assert jwt_mod.decode_access_token(forged, log_expired=False) is None

    expired = jwt_mod.create_access_token(
        {"sub": "u1", "user_id": 1},
        expires_delta=-__import__("datetime").timedelta(seconds=1),
    )
    assert jwt_mod.decode_access_token(expired, log_expired=False) is None


@pytest.mark.asyncio
async def test_security_privilege_escalation_via_session_role_is_not_enough(
    monkeypatch: pytest.MonkeyPatch,
    isolated_ctx,
):
    del isolated_ctx
    async def _secure_action(_ctx, _session, _sdk):
        return {"ok": True}

    secure_action = permission_required(["admin.secret"])(_secure_action)
    dispatcher = ActionDispatcher()
    dispatcher.register_action("secure_action", secure_action)

    engine = RequestCycleEngine()
    monkeypatch.setattr(
        "democrai.core.application.auth.service.get_user_permissions",
        lambda _user_id: ["user.read"],
    )

    session = {"user": {"id": 10, "role": "super"}}
    permissions = engine._get_permissions(10, session)
    assert permissions == ["user.read"]

    result = await dispatcher.dispatch(
        "secure_action",
        {},
        session,
        permissions=permissions,
        sdk=SimpleNamespace(module_name="core"),
    )
    assert result.get("error") == "permission_denied"


@pytest.mark.asyncio
async def test_guest_request_can_call_only_public_actions():
    async def _private_action(_ctx, _session, _sdk):
        return {"ok": True}

    @public
    async def _public_action(_ctx, _session, _sdk):
        return {"ok": True}

    dispatcher = ActionDispatcher()
    dispatcher.register_action("private_action", _private_action)
    dispatcher.register_action("public_action", _public_action)

    token = set_req_ctx(
        RequestContext(
            app=app_ctx(),
            request_id="guest-action",
            user=None,
            role=None,
            organization_id=None,
            access_level=None,
            channel="test",
        )
    )
    try:
        denied = await dispatcher.dispatch(
            "private_action",
            {},
            {},
            permissions=[],
            sdk=SimpleNamespace(module_name="core"),
        )
        allowed = await dispatcher.dispatch(
            "public_action",
            {},
            {},
            permissions=[],
            sdk=SimpleNamespace(module_name="core"),
        )
    finally:
        reset_req_ctx(token)

    assert denied["error"] == "authentication_required"
    assert allowed == {"ok": True}


def test_security_sql_injection_in_filters_is_not_executed(isolated_ctx):
    Base = declarative_base()

    class _Item(Base):
        __tablename__ = "security_items"
        id = Column(Integer, primary_key=True, autoincrement=True)
        user_id = Column(Integer, nullable=False, index=True)
        organization_id = Column(Integer, nullable=True, index=True)
        label = Column(String(120), nullable=False)

    engine = create_engine("sqlite:///:memory:")
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(engine)
    with SessionLocal() as session:
        session.add_all(
            [
                _Item(user_id=1, organization_id=10, label="alpha"),
                _Item(user_id=1, organization_id=10, label="beta"),
            ]
        )
        session.commit()

    isolated_ctx.data_store = SimpleNamespace(get_session=SessionLocal)
    store = DataStore(user_id=1, organization_id=10, access_level=3)
    rows = store.list(_Item, label="'; DROP TABLE users;--")
    assert rows == []

    with SessionLocal() as session:
        assert session.query(_Item).count() == 2


def test_security_media_provider_blocks_path_traversal(tmp_path: Path):
    provider = LocalMediaProvider(str(tmp_path / "assets"))
    with pytest.raises(ValueError, match="escapes media base directory"):
        provider.save("../../../etc/passwd", b"boom")


def test_security_network_policy_blocks_undeclared_socket_target(tmp_path: Path):
    allowed = tmp_path / "allowed"
    allowed.mkdir(parents=True, exist_ok=True)
    with process_guard_context(
        subject="security.net",
        allowed_paths=[str(allowed)],
        allowed_targets=["https://allowed.local"],
        allow_subprocess=False,
    ):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            with pytest.raises(PermissionError):
                sock.connect(("example.com", 80))
        finally:
            sock.close()


def test_security_network_policy_blocks_undeclared_http_target(tmp_path: Path):
    allowed = tmp_path / "allowed"
    allowed.mkdir(parents=True, exist_ok=True)
    with process_guard_context(
        subject="security.net.http",
        allowed_paths=[str(allowed)],
        allowed_targets=["https://allowed.local"],
        allow_subprocess=False,
    ):
        with pytest.raises(PermissionError):
            urllib.request.urlopen("https://example.com", timeout=0.1)  # noqa: S310


def test_security_network_policy_blocks_undeclared_httpx_target(tmp_path: Path):
    httpx = pytest.importorskip("httpx")
    allowed = tmp_path / "allowed"
    allowed.mkdir(parents=True, exist_ok=True)
    with process_guard_context(
        subject="security.net.httpx",
        allowed_paths=[str(allowed)],
        allowed_targets=["https://allowed.local"],
        allow_subprocess=False,
    ):
        with pytest.raises(PermissionError):
            with httpx.Client(timeout=0.1) as client:
                client.get("https://example.com")


@pytest.mark.asyncio
async def test_security_network_policy_blocks_undeclared_aiohttp_target(tmp_path: Path):
    aiohttp = pytest.importorskip("aiohttp")
    allowed = tmp_path / "allowed"
    allowed.mkdir(parents=True, exist_ok=True)
    with process_guard_context(
        subject="security.net.aiohttp",
        allowed_paths=[str(allowed)],
        allowed_targets=["https://allowed.local"],
        allow_subprocess=False,
    ):
        with pytest.raises(PermissionError):
            async with aiohttp.ClientSession() as client:
                await client.get("https://example.com")


@pytest.mark.asyncio
async def test_security_action_spoofing_unknown_prefixed_action_rejected(isolated_ctx):
    del isolated_ctx
    dispatcher = ActionDispatcher()
    out = await dispatcher.dispatch(
        "system.safe_action",
        {},
        {},
        permissions=[],
        sdk=SimpleNamespace(module_name="core"),
    )
    assert out.get("error") == "unknown_action"


@pytest.mark.asyncio
async def test_security_cross_org_escalation_via_ctx_filters_is_blocked(isolated_ctx):
    Base = declarative_base()

    class _Record(Base):
        __tablename__ = "security_org_records"
        id = Column(Integer, primary_key=True, autoincrement=True)
        user_id = Column(Integer, nullable=False, index=True)
        organization_id = Column(Integer, nullable=False, index=True)
        label = Column(String(120), nullable=False)

    class _RecordModel(BaseCoreModel):
        name = "security_org_records"
        sqlalchemy_model = _Record

        def serialize_row(self, item):
            return {
                "id": int(item.id),
                "user_id": int(item.user_id),
                "organization_id": int(item.organization_id),
                "label": str(item.label),
            }

        def filters_model(self):
            return [
                {"field": "organization_id", "type": "int"},
                {"field": "label", "type": "text"},
            ]

        def table_model(self):
            return [{"field": "id"}, {"field": "organization_id"}, {"field": "label"}]

        def create(self, payload):
            raise NotImplementedError

        def update(self, entity_id, payload):
            raise NotImplementedError

        def delete(self, entity_id):
            raise NotImplementedError

    engine = create_engine("sqlite:///:memory:")
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(engine)
    with SessionLocal() as session:
        session.add_all(
            [
                _Record(user_id=1, organization_id=10, label="org10"),
                _Record(user_id=2, organization_id=20, label="org20"),
            ]
        )
        session.commit()

    async def _list_action(ctx, session, _sdk):
        user = dict(session.get("user") or {})
        model = _RecordModel(
            CoreModelContext(
                user_id=int(user.get("id") or 0),
                organization_id=int(user.get("organization_id") or 0),
                access_level=int(user.get("access_level") or ROLE_LEVEL_ORGANIZATION),
                module_name="core",
                session=session,
            )
        )
        model._session_factory = lambda: SessionLocal
        listing = model.list(filters=dict(ctx.get("filters") or {}), page=0, page_size=50)
        return {"rows": listing["rows"]}

    dispatcher = ActionDispatcher()
    dispatcher.register_action("security_list_records", _list_action)

    session = {
        "user": {
            "id": 999,
            "organization_id": 10,
            "access_level": ROLE_LEVEL_ORGANIZATION,
            "role": "organization",
        }
    }
    result = await dispatcher.dispatch(
        "security_list_records",
        {"filters": {"organization_id": 20, "label": "org"}},
        session,
        permissions=[],
        sdk=SimpleNamespace(module_name="core"),
    )
    rows = result.get("rows") or []
    assert rows == []

    allowed = await dispatcher.dispatch(
        "security_list_records",
        {"filters": {"label": "org"}},
        session,
        permissions=[],
        sdk=SimpleNamespace(module_name="core"),
    )
    rows = allowed.get("rows") or []
    assert len(rows) == 1
    assert rows[0]["organization_id"] == 10


def test_security_session_leakage_stress():
    store = SessionStore()
    service = SessionService(store)
    errors: list[str] = []

    def _worker(user_id: int):
        for i in range(50):
            session = service.get_or_create(user_id, "User")
            session["marker"] = f"user-{user_id}-{i}"
            key = service._storage_key_for_identity(user_id)
            service.persist(key)
            loaded = service.get_or_create(user_id, "User")
            if loaded.get("marker") != f"user-{user_id}-{i}":
                errors.append(f"mismatch:{user_id}:{i}")

    threads = [threading.Thread(target=_worker, args=(uid,)) for uid in range(1, 41)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []


@pytest.mark.asyncio
async def test_security_event_flooding_does_not_deadlock(monkeypatch: pytest.MonkeyPatch):
    calls = {"count": 0}
    listeners_prev = dict(module_event_registry._listeners)  # pylint: disable=protected-access
    definitions_prev = dict(module_event_registry._definitions)  # pylint: disable=protected-access
    order_prev = module_event_registry._registration_order  # pylint: disable=protected-access

    async def _listener(payload, event_name):
        del payload
        del event_name
        calls["count"] += 1
        return True

    try:
        module_event_registry._listeners = {}  # pylint: disable=protected-access
        module_event_registry._definitions = {}  # pylint: disable=protected-access
        module_event_registry._registration_order = 0  # pylint: disable=protected-access
        module_event_registry.register("security.flood", _listener, module_name="core")

        async def _flood():
            for i in range(10_000):
                await emit_module_event("security.flood", payload={"i": i}, session={})

        await asyncio.wait_for(_flood(), timeout=20.0)
        assert calls["count"] == 10_000
    finally:
        module_event_registry._listeners = listeners_prev  # pylint: disable=protected-access
        module_event_registry._definitions = definitions_prev  # pylint: disable=protected-access
        module_event_registry._registration_order = order_prev  # pylint: disable=protected-access


def test_security_module_core_import_boundary_is_blocked(tmp_path: Path, isolated_ctx):
    del isolated_ctx
    module_name = "security_boundary_module"
    module_dir = tmp_path / module_name
    (module_dir / "actions").mkdir(parents=True)
    (module_dir / "__init__.py").write_text("", encoding="utf-8")
    (module_dir / "actions" / "__init__.py").write_text(
        "\n".join(
            [
                "from democrai.core.runtime.foundation.app import app_ctx",
                "from democrai.sdk.decorators import action",
                "",
                '@action("boundary_probe")',
                "async def boundary_probe(ctx, session, module_sdk):",
                "    del ctx, session, module_sdk",
                "    return {'ok': bool(app_ctx())}",
            ]
        ),
        encoding="utf-8",
    )
    (module_dir / "manifest.json").write_text(
        '{"name":"security_boundary_module","label":"Security Boundary","version":"1.0.0","enabled":true}',
        encoding="utf-8",
    )

    manager = ModuleManager()
    manager._try_register_module(str(module_dir), is_builtin=False, load_ui=False)  # pylint: disable=protected-access
    loaded = manager.get_module(module_name)
    assert loaded is None or not loaded.is_active


def test_security_module_sdk_import_boundary_is_allowed(tmp_path: Path, isolated_ctx):
    module_name = "securitysdkboundary"
    module_dir = tmp_path / module_name
    (module_dir / "actions").mkdir(parents=True)
    (module_dir / "__init__.py").write_text("", encoding="utf-8")
    (module_dir / "actions" / "__init__.py").write_text(
        "\n".join(
            [
                "from democrai.sdk.decorators import action",
                "",
                '@action("sdk_boundary_probe")',
                "async def sdk_boundary_probe(ctx, session, module_sdk):",
                "    _ = (ctx, session, module_sdk)",
                "    return {'ok': True}",
            ]
        ),
        encoding="utf-8",
    )
    (module_dir / "manifest.json").write_text(
        '{"name":"securitysdkboundary","label":"Security SDK Boundary","version":"1.0.0","enabled":true,"allowed_imports":["democrai"]}',
        encoding="utf-8",
    )

    manager = ModuleManager()
    manager._try_register_module(str(module_dir), is_builtin=False, load_ui=False)  # pylint: disable=protected-access
    loaded = manager.get_module(module_name)
    assert loaded is not None and loaded.is_active


def test_security_module_core_lazy_import_boundary_is_blocked(tmp_path: Path, isolated_ctx):
    del isolated_ctx
    module_name = "security_boundary_lazy_module"
    module_dir = tmp_path / module_name
    (module_dir / "actions").mkdir(parents=True)
    (module_dir / "__init__.py").write_text("", encoding="utf-8")
    (module_dir / "actions" / "__init__.py").write_text(
        "\n".join(
            [
                "import importlib",
                "from democrai.sdk.decorators import action",
                "",
                '@action("boundary_lazy_probe")',
                "async def boundary_lazy_probe(ctx, session, module_sdk):",
                "    del ctx, session, module_sdk",
                '    return {"ok": bool(importlib.import_module("democrai.core.runtime.foundation.app"))}',
            ]
        ),
        encoding="utf-8",
    )
    (module_dir / "manifest.json").write_text(
        '{"name":"security_boundary_lazy_module","label":"Security Boundary Lazy","version":"1.0.0","enabled":true}',
        encoding="utf-8",
    )

    manager = ModuleManager()
    manager._try_register_module(str(module_dir), is_builtin=False, load_ui=False)  # pylint: disable=protected-access
    loaded = manager.get_module(module_name)
    assert loaded is None or not loaded.is_active


def test_security_module_core_lazy_import_via_variable_is_blocked(tmp_path: Path, isolated_ctx):
    del isolated_ctx
    module_name = "security_boundary_lazy_var_module"
    module_dir = tmp_path / module_name
    (module_dir / "actions").mkdir(parents=True)
    (module_dir / "__init__.py").write_text("", encoding="utf-8")
    (module_dir / "actions" / "__init__.py").write_text(
        "\n".join(
            [
                "import importlib",
                "from democrai.sdk.decorators import action",
                "",
                '@action("boundary_lazy_var_probe")',
                "async def boundary_lazy_var_probe(ctx, session, module_sdk):",
                "    del ctx, session, module_sdk",
                '    target = "democrai.core.runtime.foundation.app"',
                "    return {'ok': bool(importlib.import_module(target))}",
            ]
        ),
        encoding="utf-8",
    )
    (module_dir / "manifest.json").write_text(
        '{"name":"security_boundary_lazy_var_module","label":"Security Boundary Lazy Var","version":"1.0.0","enabled":true}',
        encoding="utf-8",
    )

    manager = ModuleManager()
    manager._try_register_module(str(module_dir), is_builtin=False, load_ui=False)  # pylint: disable=protected-access
    loaded = manager.get_module(module_name)
    assert loaded is None or not loaded.is_active


def test_security_module_core_lazy_import_via_string_concat_is_blocked(tmp_path: Path, isolated_ctx):
    del isolated_ctx
    module_name = "security_boundary_lazy_concat_module"
    module_dir = tmp_path / module_name
    (module_dir / "actions").mkdir(parents=True)
    (module_dir / "__init__.py").write_text("", encoding="utf-8")
    (module_dir / "actions" / "__init__.py").write_text(
        "\n".join(
            [
                "import importlib",
                "from democrai.sdk.decorators import action",
                "",
                '@action("boundary_lazy_concat_probe")',
                "async def boundary_lazy_concat_probe(ctx, session, module_sdk):",
                "    del ctx, session, module_sdk",
                '    target = "democrai.co" + "re.runtime.foundation.app"',
                "    return {'ok': bool(importlib.import_module(target))}",
            ]
        ),
        encoding="utf-8",
    )
    (module_dir / "manifest.json").write_text(
        '{"name":"security_boundary_lazy_concat_module","label":"Security Boundary Lazy Concat","version":"1.0.0","enabled":true}',
        encoding="utf-8",
    )

    manager = ModuleManager()
    manager._try_register_module(str(module_dir), is_builtin=False, load_ui=False)  # pylint: disable=protected-access
    loaded = manager.get_module(module_name)
    assert loaded is None or not loaded.is_active


def test_security_module_core_lazy_import_via_fstring_is_blocked(tmp_path: Path, isolated_ctx):
    del isolated_ctx
    module_name = "security_boundary_lazy_fstring_module"
    module_dir = tmp_path / module_name
    (module_dir / "actions").mkdir(parents=True)
    (module_dir / "__init__.py").write_text("", encoding="utf-8")
    (module_dir / "actions" / "__init__.py").write_text(
        "\n".join(
            [
                "import importlib",
                "from democrai.sdk.decorators import action",
                "",
                '@action("boundary_lazy_fstring_probe")',
                "async def boundary_lazy_fstring_probe(ctx, session, module_sdk):",
                "    del ctx, session, module_sdk",
                '    prefix = "democrai.core"',
                '    target = f"{prefix}.runtime.foundation.app"',
                "    return {'ok': bool(importlib.import_module(target))}",
            ]
        ),
        encoding="utf-8",
    )
    (module_dir / "manifest.json").write_text(
        '{"name":"security_boundary_lazy_fstring_module","label":"Security Boundary Lazy Fstring","version":"1.0.0","enabled":true}',
        encoding="utf-8",
    )

    manager = ModuleManager()
    manager._try_register_module(str(module_dir), is_builtin=False, load_ui=False)  # pylint: disable=protected-access
    loaded = manager.get_module(module_name)
    assert loaded is None or not loaded.is_active


def test_security_module_core_lazy_import_via_augassign_concat_is_blocked(tmp_path: Path, isolated_ctx):
    del isolated_ctx
    module_name = "security_boundary_lazy_augassign_module"
    module_dir = tmp_path / module_name
    (module_dir / "actions").mkdir(parents=True)
    (module_dir / "__init__.py").write_text("", encoding="utf-8")
    (module_dir / "actions" / "__init__.py").write_text(
        "\n".join(
            [
                "import importlib",
                "from democrai.sdk.decorators import action",
                "",
                '@action("boundary_lazy_augassign_probe")',
                "async def boundary_lazy_augassign_probe(ctx, session, module_sdk):",
                "    del ctx, session, module_sdk",
                '    target = "democrai.co"',
                '    target += "re.runtime.foundation.app"',
                "    return {'ok': bool(importlib.import_module(target))}",
            ]
        ),
        encoding="utf-8",
    )
    (module_dir / "manifest.json").write_text(
        '{"name":"security_boundary_lazy_augassign_module","label":"Security Boundary Lazy AugAssign","version":"1.0.0","enabled":true}',
        encoding="utf-8",
    )

    manager = ModuleManager()
    manager._try_register_module(str(module_dir), is_builtin=False, load_ui=False)  # pylint: disable=protected-access
    loaded = manager.get_module(module_name)
    assert loaded is None or not loaded.is_active


def test_security_module_core_lazy_import_direct_concat_call_is_blocked(tmp_path: Path, isolated_ctx):
    del isolated_ctx
    module_name = "security_boundary_lazy_direct_concat_module"
    module_dir = tmp_path / module_name
    (module_dir / "actions").mkdir(parents=True)
    (module_dir / "__init__.py").write_text("", encoding="utf-8")
    (module_dir / "actions" / "__init__.py").write_text(
        "\n".join(
            [
                "import importlib",
                "from democrai.sdk.decorators import action",
                "",
                '@action("boundary_lazy_direct_concat_probe")',
                "async def boundary_lazy_direct_concat_probe(ctx, session, module_sdk):",
                "    del ctx, session, module_sdk",
                '    return {"ok": bool(importlib.import_module("democrai.co" + "re.runtime.foundation.app"))}',
            ]
        ),
        encoding="utf-8",
    )
    (module_dir / "manifest.json").write_text(
        '{"name":"security_boundary_lazy_direct_concat_module","label":"Security Boundary Lazy Direct Concat","version":"1.0.0","enabled":true}',
        encoding="utf-8",
    )

    manager = ModuleManager()
    manager._try_register_module(str(module_dir), is_builtin=False, load_ui=False)  # pylint: disable=protected-access
    loaded = manager.get_module(module_name)
    assert loaded is None or not loaded.is_active


def test_security_module_dynamic_import_allowed_when_fail_closed_disabled(tmp_path: Path, isolated_ctx):
    del isolated_ctx
    module_name = "securitydynamicimportallowed"
    module_dir = tmp_path / module_name
    (module_dir / "actions").mkdir(parents=True)
    (module_dir / "__init__.py").write_text("", encoding="utf-8")
    (module_dir / "actions" / "__init__.py").write_text(
        "\n".join(
            [
                "import importlib",
                "from democrai.sdk.decorators import action",
                "",
                '@action("dynamic_allowed_probe")',
                "async def dynamic_allowed_probe(ctx, session, module_sdk):",
                "    del ctx, session, module_sdk",
                '    target = "json"',
                "    loaded = importlib.import_module(target)",
                "    return {'ok': bool(loaded)}",
            ]
        ),
        encoding="utf-8",
    )
    (module_dir / "manifest.json").write_text(
        '{"name":"securitydynamicimportallowed","label":"Dynamic Import Allowed","version":"1.0.0","enabled":true,"allowed_imports":["sdk","importlib","json"]}',
        encoding="utf-8",
    )

    manager = ModuleManager()
    manager._try_register_module(str(module_dir), is_builtin=False, load_ui=False)  # pylint: disable=protected-access
    loaded = manager.get_module(module_name)
    assert loaded is not None and loaded.is_active


def test_security_module_dynamic_import_blocked_when_fail_closed_enabled(tmp_path: Path, isolated_ctx):
    isolated_ctx.config = SimpleNamespace(
        get=lambda key, default=None: (
            True if key == "modules.sdk_boundary.fail_closed_dynamic_imports" else default
        )
    )
    module_name = "security_dynamic_import_blocked_module"
    module_dir = tmp_path / module_name
    (module_dir / "actions").mkdir(parents=True)
    (module_dir / "__init__.py").write_text("", encoding="utf-8")
    (module_dir / "actions" / "__init__.py").write_text(
        "\n".join(
            [
                "import importlib",
                "from democrai.sdk.decorators import action",
                "",
                '@action("dynamic_blocked_probe")',
                "async def dynamic_blocked_probe(ctx, session, module_sdk):",
                "    del ctx, session, module_sdk",
                '    target = "json"',
                "    loaded = importlib.import_module(target)",
                "    return {'ok': bool(loaded)}",
            ]
        ),
        encoding="utf-8",
    )
    (module_dir / "manifest.json").write_text(
        '{"name":"security_dynamic_import_blocked_module","label":"Dynamic Import Blocked","version":"1.0.0","enabled":true}',
        encoding="utf-8",
    )

    manager = ModuleManager()
    manager._try_register_module(str(module_dir), is_builtin=False, load_ui=False)  # pylint: disable=protected-access
    loaded = manager.get_module(module_name)
    assert loaded is None or not loaded.is_active


@pytest.mark.asyncio
async def test_security_recursive_action_has_depth_limit():
    dispatcher = ActionDispatcher()

    async def _recursive(ctx, session, sdk):
        depth = int(session.get("_depth", 0))
        session["_depth"] = depth + 1
        return await dispatcher.dispatch("recursive_action", ctx, session, [], sdk)

    dispatcher.register_action("recursive_action", _recursive)
    out = await asyncio.wait_for(
        dispatcher.dispatch(
            "recursive_action",
            {},
            {"_depth": 0},
            [],
            SimpleNamespace(module_name="core"),
        ),
        timeout=2.0,
    )
    assert out.get("error") == "recursion_limit_exceeded"
