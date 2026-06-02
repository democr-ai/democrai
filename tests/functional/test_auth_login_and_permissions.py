import asyncio
import sys
import types
import importlib


def _identity_action(_name=None):
    def deco(fn):
        return fn

    return deco


class _SdkModule:
    def event_slot(self, *_args, **_kwargs):
        return _identity_action()


sys.modules.setdefault(
    "sdk",
    types.SimpleNamespace(action=_identity_action, sdk=_SdkModule()),
)

from democrai.core.runtime.foundation.app import app_ctx

_JWT_SECRET = "a-very-long-and-secure-secret-key-for-testing"
app_ctx().config = types.SimpleNamespace(get=lambda k, d=None: _JWT_SECRET if k == "auth.jwt_secret" else d)
app_ctx().logger = types.SimpleNamespace(
    info=lambda *a, **k: None,
    error=lambda *a, **k: None,
    warning=lambda *a, **k: None,
    debug=lambda *a, **k: None,
)

from modules.auth.actions import go_login, login


class _Users:
    def __init__(self, should_verify: bool, info=None):
        self._ok = should_verify
        self._info = info or {}

    def verify(self, username: str, password: str) -> bool:
        return self._ok

    def get_info(self, username: str):
        return self._info if self._ok else None


class _Auth:
    def __init__(self, users):
        self.users = users

    def create_token(self, payload, expires_delta=None):
        from democrai.core.application.auth.jwt import create_access_token
        return create_access_token(payload, expires_delta)

    def login(self, username: str, password: str):
        if not self.users.verify(username, password):
            return {"ok": False, "error": "invalid_credentials", "details": "Invalid credentials."}
        user_info = self.users.get_info(username) or {}
        token_payload = {
            "user_id": user_info.get("id"),
            "username": user_info.get("username") or username,
            "role": "super",
            "access_level": 3,
            "organization_id": None,
        }
        return {
            "ok": True,
            "user_id": user_info.get("id"),
            "user_info": user_info,
            "token_payload": token_payload,
            "token": self.create_token(token_payload),
        }


class _SDK:
    def __init__(self, users):
        self.models = types.SimpleNamespace(users=users)
        self.auth = _Auth(users)
        self.logged = []
        self.system = types.SimpleNamespace(log=lambda msg, level="info": self.logged.append((level, msg)))
        self.effects = types.SimpleNamespace(
            render=lambda: {"type": "render"},
            refresh_modules=lambda: {"type": "refresh_modules"},
            set_jwt=lambda token: {"type": "set_jwt", "token": token},
            ui_messages=lambda msgs: {"type": "ui_messages", "messages": list(msgs)},
            notify=lambda channel, payload: {"type": "notify", "channel": channel, "payload": payload},
            respond=lambda *effects: {"effects": list(effects)},
        )
        self.events = types.SimpleNamespace(emit=self._emit_event)
        self.pages = types.SimpleNamespace(
            get_post_login_redirect_path=lambda: "/dashboard/index",
            get_guest_path=lambda: "/auth/login",
        )
        self.i18n = types.SimpleNamespace(get_user_language=lambda _user_id: "en")

    async def _emit_event(self, *_args, **_kwargs):
        return None


def test_login_submit_success_updates_session_and_returns_effects():
    session = {}
    sdk = _SDK(
        _Users(
            True,
            info={"id": 1, "username": "fabio", "roles": ["Admin"]},
        )
    )

    result = asyncio.run(
        login({"login_form": {"username": "fabio", "password": "pw"}}, session, sdk)
    )

    assert "effects" in result
    assert session["user"]["username"] == "fabio"
    assert session["user"]["role"] == "super"
    assert session["user"]["access_level"] == 3
    assert session["current_path"] == "/dashboard/index"
    assert any(e.get("type") == "set_jwt" for e in result["effects"])


def test_login_submit_invalid_credentials_returns_error():
    session = {}
    sdk = _SDK(_Users(False))

    result = asyncio.run(
        login({"login_form": {"username": "fabio", "password": "wrong"}}, session, sdk)
    )

    assert "effects" in result
    assert result["effects"][0]["type"] == "ui_messages"
    toast = result["effects"][0]["messages"][0]["eventNotification"]
    assert toast["title"] == "Login failed"
    assert "Invalid credentials" in toast["text"]


def test_go_login_restores_canonical_guest_session():
    session = {
        "user": {"username": "fabio", "id": 1, "role": "super"},
        "user_language": "it",
        "current_path": "/dashboard/index",
        "other": "value",
    }
    sdk = _SDK(_Users(False))

    result = asyncio.run(go_login(session=session, module_sdk=sdk))

    assert result["effects"][0]["type"] == "render"
    assert result["effects"][1]["type"] == "refresh_modules"
    assert result["effects"][2] == {"type": "set_jwt", "token": ""}
    assert session["current_path"] == "/auth/login"
    assert session["user"] == {
        "username": "guest",
        "id": "guest",
        "role": "Guest",
        "access_level": 99,
        "organization_id": None,
        "avatar": "user",
    }
    assert session["user_language"] == "it"
    assert "other" not in session


def test_login_submit_locks_after_too_many_attempts():
    auth_actions = importlib.import_module("modules.auth.actions")
    session = {}
    sdk = _SDK(_Users(False))
    sdk.auth.login = lambda _username, _password: {
        "ok": False,
        "error": "rate_limited",
        "details": "Too many attempts. Please try again later.",
    }

    result = asyncio.run(
        auth_actions.login({"login_form": {"username": "fabio", "password": "wrong"}}, session, sdk)
    )

    toast = result["effects"][0]["messages"][0]["eventNotification"]
    assert toast["title"] == "Login blocked"
    assert "Too many attempts" in toast["text"]
