from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import democrai.core.application.auth.service as auth_service_mod
import democrai.core.application.services.translation as translation_mod
from democrai.core.application.handler.dispatcher import ActionDispatcher
from democrai.core.infrastructure.modules.manager import ModuleManager
from democrai.core.infrastructure.storage.media.providers.local import LocalMediaProvider
from democrai.core.infrastructure.database.models import Base as AuthBase
from democrai.core.infrastructure.database.models import Permission
from democrai.core.platform.config.yaml_config import YamlConfigProvider
from democrai.sdk.client import SDK as ModuleSDK
from democrai.core.runtime.bootstrap.config_validation import validate_config_provider
from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.runtime.foundation.app import request_context_scope
from democrai.core.runtime.foundation.registry import action_registry


def _silent_logger() -> SimpleNamespace:
    return SimpleNamespace(
        debug=lambda *a, **k: None,
        info=lambda *a, **k: None,
        warning=lambda *a, **k: None,
        error=lambda *a, **k: None,
    )


@pytest.fixture()
def isolated_runtime_state():
    ctx = app_ctx()
    previous_modules = ctx.modules
    previous_logger = getattr(ctx, "logger", None)
    previous_setup_mode = getattr(ctx, "setup_mode", False)
    previous_module_runtime = getattr(ctx, "module_runtime", None)
    previous_media = getattr(ctx, "media", None)

    tx_service = translation_mod._tx_service  # pylint: disable=protected-access
    tx_snapshot = (
        tx_service._loaded,  # pylint: disable=protected-access
        tx_service._default_language,  # pylint: disable=protected-access
        {lang: dict(values) for lang, values in tx_service._translations.items()},  # pylint: disable=protected-access
        set(tx_service._loaded_locale_paths),  # pylint: disable=protected-access
    )

    registry_actions_prev = dict(action_registry.actions)
    registry_functions_prev = dict(action_registry.functions)
    registry_commands_prev = dict(action_registry.commands)

    manager = ModuleManager()
    ctx.modules = manager
    ctx.logger = _silent_logger()
    ctx.setup_mode = False
    ctx.module_runtime = None
    ctx.media = None

    try:
        yield manager
    finally:
        action_registry.actions = registry_actions_prev
        action_registry.functions = registry_functions_prev
        action_registry.commands = registry_commands_prev
        (
            tx_service._loaded,  # pylint: disable=protected-access
            tx_service._default_language,  # pylint: disable=protected-access
            tx_service._translations,  # pylint: disable=protected-access
            tx_service._loaded_locale_paths,  # pylint: disable=protected-access
        ) = tx_snapshot
        ctx.modules = previous_modules
        ctx.logger = previous_logger
        ctx.setup_mode = previous_setup_mode
        ctx.module_runtime = previous_module_runtime
        ctx.media = previous_media


def _write_module(
    root: Path,
    *,
    module_name: str,
    actions_py: str,
    manifest: dict | None = None,
    rbac: dict | None = None,
    locales: dict[str, dict[str, str]] | None = None,
) -> Path:
    module_dir = root / module_name
    (module_dir / "actions").mkdir(parents=True)
    (module_dir / "__init__.py").write_text("", encoding="utf-8")
    (module_dir / "actions" / "__init__.py").write_text(actions_py, encoding="utf-8")
    (module_dir / "manifest.json").write_text(
        json.dumps(
            manifest
            or {
                "name": module_name,
                "label": module_name,
                "version": "1.0.0",
                "enabled": True,
                "allowed_imports": ["sdk"],
            }
        ),
        encoding="utf-8",
    )
    if rbac is not None:
        (module_dir / "rbac.json").write_text(json.dumps(rbac), encoding="utf-8")
    if locales:
        locales_dir = module_dir / "locales"
        locales_dir.mkdir(parents=True, exist_ok=True)
        for lang, payload in locales.items():
            (locales_dir / f"{lang}.json").write_text(json.dumps(payload), encoding="utf-8")
    return module_dir


@pytest.mark.asyncio
async def test_functional_action_dispatch_end_to_end(isolated_runtime_state: ModuleManager, tmp_path: Path):
    module_name = "functionaldispatch"
    actions_py = "\n".join(
        [
            "from democrai.sdk.decorators import action",
            "from sdk.auth import permission_required",
            "",
            '@action("dispatch_secure")',
            f'@permission_required(["{module_name}.entity.create"])',
            "async def dispatch_secure(ctx, session, module_sdk):",
            '    session["dispatch_seen"] = ctx.get("value")',
            "    return module_sdk.effects.respond(",
            '        module_sdk.effects.navigate("/ok", render=True),',
            '        module_sdk.effects.ui_messages([{"eventNotification": {"title": "ok", "text": "done", "type": "success"}}]),',
            "    )",
            "",
        ]
    )
    module_dir = _write_module(tmp_path, module_name=module_name, actions_py=actions_py)
    isolated_runtime_state._try_register_module(str(module_dir), is_builtin=False, load_ui=False)  # pylint: disable=protected-access
    assert isolated_runtime_state.get_module(module_name) is not None

    dispatcher = ActionDispatcher()
    session = {
        "current_path": f"/{module_name}/index",
        "user": {"id": 42, "username": "dispatch", "role": "User", "access_level": 3},
    }
    sdk = ModuleSDK("", "core", session=session)

    denied = await dispatcher.dispatch(
        "dispatch_secure",
        {"value": 7},
        session,
        permissions=[],
        sdk=sdk,
    )
    assert denied["error"] == "permission_denied"

    allowed = await dispatcher.dispatch(
        "dispatch_secure",
        {"value": 7},
        session,
        permissions=[f"{module_name}.entity.create"],
        sdk=sdk,
    )
    assert "effects" in allowed
    assert session["dispatch_seen"] == 7
    assert any(effect.get("type") == "navigate" for effect in allowed["effects"])
    assert any(effect.get("type") == "ui_messages" for effect in allowed["effects"])
    json.dumps(allowed["effects"])


def test_functional_i18n_translation_loading_by_session_language(
    isolated_runtime_state: ModuleManager, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    assert hasattr(translation_mod, "get_preference")
    monkeypatch.setattr(translation_mod, "get_preference", lambda *_a, **_k: "en")
    module_name = "functionali18n"
    actions_py = "from democrai.sdk.decorators import action\n"
    module_dir = _write_module(
        tmp_path,
        module_name=module_name,
        actions_py=actions_py,
        locales={
            "en": {"hello": "Hello", f"{module_name}.welcome": "Welcome"},
            "it": {"hello": "Ciao", f"{module_name}.welcome": "Benvenuto"},
        },
    )
    isolated_runtime_state._try_register_module(str(module_dir), is_builtin=False, load_ui=False)  # pylint: disable=protected-access

    sdk_it = ModuleSDK(
        module_path=str(module_dir),
        module_name=module_name,
        session={"user_language": "it", "user": {"id": "anonymous"}},
    )
    sdk_en = ModuleSDK(
        module_path=str(module_dir),
        module_name=module_name,
        session={"user_language": "en", "user": {"id": "anonymous"}},
    )

    assert sdk_it.i18n.t(f"{module_name}.hello") == "Ciao"
    assert sdk_it.i18n.t(f"{module_name}.welcome") == "Benvenuto"
    assert sdk_en.i18n.t(f"{module_name}.hello") == "Hello"
    assert sdk_en.i18n.t(f"{module_name}.welcome") == "Welcome"


@pytest.mark.asyncio
async def test_functional_rbac_sync_from_rbac_json_and_permission_gate(
    isolated_runtime_state: ModuleManager, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    db_path = tmp_path / "rbac.sqlite"
    engine = create_engine(f"sqlite:///{db_path}")
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    AuthBase.metadata.create_all(engine)
    monkeypatch.setattr(auth_service_mod, "SessionLocal", SessionLocal)

    module_name = "functionalrbac"
    actions_py = "\n".join(
        [
            "from democrai.sdk.decorators import action",
            "from sdk.auth import permission_required",
            "",
            '@action("rbac_create")',
            f'@permission_required(["{module_name}.entity.create"])',
            "async def rbac_create(ctx, session, module_sdk):",
            "    return module_sdk.effects.respond(module_sdk.effects.render())",
            "",
        ]
    )
    module_dir = _write_module(
        tmp_path,
        module_name=module_name,
        actions_py=actions_py,
        rbac={
            "permissions": ["entity.list", "entity.create"],
            "roles": [{"name": "manager"}],
            "assignments": {"manager": ["entity.list", "entity.create"]},
        },
    )
    isolated_runtime_state._try_register_module(str(module_dir), is_builtin=False, load_ui=False)  # pylint: disable=protected-access
    loaded = isolated_runtime_state.get_module(module_name)
    assert loaded is not None and loaded.is_active

    with SessionLocal() as db:
        permissions = {item.name for item in db.query(Permission).all()}
    assert f"{module_name}.entity.list" in permissions
    assert f"{module_name}.entity.create" in permissions

    dispatcher = ActionDispatcher()
    session = {
        "current_path": f"/{module_name}/index",
        "user": {"id": 9, "username": "rbac", "role": "User", "access_level": 3},
    }
    sdk = ModuleSDK("", "core", session=session)

    denied = await dispatcher.dispatch("rbac_create", {}, session, permissions=[], sdk=sdk)
    assert denied["error"] == "permission_denied"

    allowed = await dispatcher.dispatch(
        "rbac_create",
        {},
        session,
        permissions=[f"{module_name}.entity.create"],
        sdk=sdk,
    )
    assert "effects" in allowed
    assert allowed["effects"][0]["type"] == "render"


def test_functional_media_provider_local_upload_and_retrieve(
    isolated_runtime_state: ModuleManager, tmp_path: Path
):
    media_root = tmp_path / "assets"
    provider = LocalMediaProvider(str(media_root))
    db_engine = create_engine(f"sqlite:///{tmp_path / 'media.sqlite'}")
    SessionLocal = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)
    AuthBase.metadata.create_all(db_engine)
    previous_db = getattr(app_ctx(), "db", None)
    app_ctx().media = provider
    app_ctx().db = SimpleNamespace(get_session=lambda: SessionLocal())

    sdk = ModuleSDK(module_path="", module_name="core", session={})
    path = "functional/media/sample.bin"
    payload = b"functional-media-payload"

    try:
        with request_context_scope(
            {
                "request_id": "media-test",
                "user": 0,
                "organization_id": None,
                "access_level": 3,
                "channel": "test",
                "module_name": "core",
            }
        ):
            saved = sdk.media.add(path, payload)
            assert saved.startswith("media/core/uid_0/")
            assert saved.endswith("_sample.bin")
            assert (media_root / saved).exists()
            assert sdk.media.view(saved) == payload

            overwritten = b"functional-media-overwrite"
            saved_overwritten = sdk.media.add(path, overwritten)
            assert saved_overwritten != saved
            assert sdk.media.view(saved) == payload
            assert sdk.media.view(saved_overwritten) == overwritten

            blocked_saved = sdk.media.add("../../../etc/passwd", b"blocked")
            assert blocked_saved.startswith("media/core/uid_0/")
            assert blocked_saved.endswith("_passwd")
            assert sdk.media.view(blocked_saved) == b"blocked"
    finally:
        app_ctx().db = previous_db
        db_engine.dispose()


def test_functional_config_bootstrap_validation_with_invalid_and_valid(tmp_path: Path):
    invalid_cfg = tmp_path / "invalid.yaml"
    invalid_cfg.write_text(
        "\n".join(
            [
                "database:",
                "  type: bad-db",
                "session:",
                "  cache:",
                "    ttl_seconds: -3",
                "auth:",
                "  jwt_secret: change-me-with-a-long-random-secret",
                "http:",
                "  cors:",
                "    enabled: true",
                "    allow_origins: ['*']",
                "    allow_credentials: true",
            ]
        ),
        encoding="utf-8",
    )
    invalid_result = validate_config_provider(
        YamlConfigProvider(str(invalid_cfg)),
        config_path=str(invalid_cfg),
    )
    assert invalid_result.ok is False
    error_messages = [issue.message for issue in invalid_result.errors]
    assert any("database.type must be one of" in msg for msg in error_messages)
    assert any("session.cache.ttl_seconds must be > 0" in msg for msg in error_messages)
    assert any("auth.jwt_secret is required" in msg for msg in error_messages)
    assert any("http.cors.allow_origins cannot contain '*'" in msg for msg in error_messages)

    valid_cfg = tmp_path / "valid.yaml"
    valid_cfg.write_text(
        "\n".join(
            [
                "auth:",
                "  jwt_secret: this-is-a-long-random-secret-for-functional-validation",
                "database:",
                "  type: sqlite",
                "http:",
                "  cors:",
                "    enabled: false",
            ]
        ),
        encoding="utf-8",
    )
    valid_result = validate_config_provider(
        YamlConfigProvider(str(valid_cfg)),
        config_path=str(valid_cfg),
    )
    assert valid_result.ok is True
    assert valid_result.errors == []
