from types import SimpleNamespace

import pytest

import democrai.core.application.auth.service as auth_service_mod


def test_module_name_and_qualification_helpers():
    assert auth_service_mod.is_valid_module_name("mod-1-a") is True
    assert auth_service_mod.is_valid_module_name("mod_1-a") is False
    assert auth_service_mod.is_valid_module_name("bad name") is False
    assert auth_service_mod.is_valid_module_name("models") is False
    assert auth_service_mod.validate_module_name("mod") == "mod"
    with pytest.raises(ValueError):
        auth_service_mod.validate_module_name("bad name")
    with pytest.raises(ValueError):
        auth_service_mod.validate_module_name("models")
    assert auth_service_mod.qualify_module_permission_name("mod", "read") == "mod.read"
    assert (
        auth_service_mod.qualify_module_permission_name("mod", "mod.read") == "mod.read"
    )
    assert auth_service_mod.qualify_module_role_name("mod", "admin") == "mod.admin"


def test_iter_named_entries_and_sync_module_authorization(monkeypatch):
    entries = auth_service_mod._iter_named_entries(
        ["a", {"name": "b", "description": "B", "permissions": ["x"]}],
        kind="permissions",
    )
    assert entries[0][0] == "a"

    perms = {}
    roles = {}

    class _DB:
        def commit(self):
            return None

        def rollback(self):
            return None

        def close(self):
            return None

    monkeypatch.setattr(
        auth_service_mod,
        "_ensure_permission",
        lambda _db, name, description=None: perms.setdefault(
            name, SimpleNamespace(name=name, description=description, roles=[])
        ),
    )
    monkeypatch.setattr(
        auth_service_mod,
        "_ensure_role",
        lambda _db, name, description=None: roles.setdefault(
            name, SimpleNamespace(name=name, description=description, permissions=[])
        ),
    )
    monkeypatch.setattr(auth_service_mod, "SessionLocal", lambda: _DB())
    monkeypatch.setattr(
        auth_service_mod,
        "app_ctx",
        lambda: SimpleNamespace(logger=SimpleNamespace(info=lambda *a, **k: None)),
    )

    auth_service_mod.sync_module_authorization(
        "mod",
        {
            "permissions": ["read", {"name": "write", "description": "w"}],
            "roles": [{"name": "editor", "permissions": ["read", "write"]}],
            "assignments": {"viewer": ["read"]},
        },
    )
    assert "mod.read" in perms and "mod.write" in perms
    assert "mod.editor" in roles and "mod.viewer" in roles


def test_password_hash_and_check():
    hashed = auth_service_mod.get_hashed_password(b"pw")
    assert isinstance(hashed, (bytes, str))
    assert auth_service_mod.check_password(b"pw", hashed) is True


def test_verify_permissions_and_profiles(monkeypatch):
    class _Perm:
        def __init__(self, name):
            self.name = name

    class _Role:
        def __init__(self, name):
            self.name = name
            self.permissions = [_Perm("p1"), _Perm("p2")]

    user_obj = SimpleNamespace(
        id=1,
        username="u1",
        email="u1@x",
        organization_id=10,
        roles=[_Role("super"), _Role("user")],
        access_level=1,
        password_hash=auth_service_mod.get_hashed_password(b"pw"),
    )

    class _Query:
        def filter(self, _expr):
            return self

        def first(self):
            return user_obj

    class _DB:
        def query(self, _model):
            return _Query()

        def close(self):
            return None

    monkeypatch.setattr(auth_service_mod, "SessionLocal", lambda: _DB())
    monkeypatch.setattr(auth_service_mod, "current_request_profiler", lambda: None)
    monkeypatch.setattr(
        auth_service_mod,
        "app_ctx",
        lambda: SimpleNamespace(logger=SimpleNamespace(error=lambda *a, **k: None)),
    )
    monkeypatch.setattr(
        auth_service_mod,
        "create_access_token",
        lambda payload: f"tok:{payload['role']}",
    )
    ok, user = auth_service_mod.verify_user("u1", b"pw")
    assert ok is True and user.username == "u1"
    assert set(auth_service_mod.get_user_permissions(1)) == {"p1", "p2"}
    profile = auth_service_mod.get_user_access_profile(1)
    assert profile["username"] == "u1"
    assert (
        auth_service_mod.get_user_access_profile_by_username("u1")["username"] == "u1"
    )


class _Span:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _Profiler:
    def span(self, _name):
        return _Span()


def test_auth_service_validation_and_named_entries_errors():
    with pytest.raises(ValueError):
        auth_service_mod.qualify_module_permission_name("mod", "")
    with pytest.raises(ValueError):
        auth_service_mod.qualify_module_role_name("mod", "")
    assert auth_service_mod.qualify_module_role_name("mod", "super") == "super"

    assert auth_service_mod._iter_named_entries(None, kind="roles") == []
    with pytest.raises(ValueError):
        auth_service_mod._iter_named_entries("bad", kind="roles")
    with pytest.raises(ValueError):
        auth_service_mod._iter_named_entries([1], kind="roles")
    with pytest.raises(ValueError):
        auth_service_mod._iter_named_entries([{}], kind="roles")


def test_ensure_role_permission_and_sync_error_paths(monkeypatch):
    class _Query:
        def __init__(self, result):
            self._result = result

        def filter(self, _expr):
            return self

        def first(self):
            return self._result

    class _DB:
        def __init__(self, role=None, perm=None):
            self.role = role
            self.perm = perm
            self.added = []
            self.rolled_back = False
            self.closed = False

        def query(self, model):
            if model is auth_service_mod.Role:
                return _Query(self.role)
            return _Query(self.perm)

        def add(self, obj):
            self.added.append(obj)

        def commit(self):
            return None

        def rollback(self):
            self.rolled_back = True

        def close(self):
            self.closed = True

    created_role_db = _DB(role=None)
    role = auth_service_mod._ensure_role(created_role_db, "demo.role", "desc")
    assert role.permissions == []

    existing_role = SimpleNamespace(description="", permissions=None)
    updated_role = auth_service_mod._ensure_role(
        _DB(role=existing_role), "demo.role", "filled"
    )
    assert updated_role.description == "filled"
    assert updated_role.permissions == []

    created_perm_db = _DB(perm=None)
    perm = auth_service_mod._ensure_permission(created_perm_db, "demo.read", "d")
    assert getattr(perm, "roles", []) == []

    existing_perm = SimpleNamespace(description="")
    updated_perm = auth_service_mod._ensure_permission(
        _DB(perm=existing_perm), "demo.read", "filled"
    )
    assert updated_perm.description == "filled"

    db = _DB()
    monkeypatch.setattr(auth_service_mod, "SessionLocal", lambda: db)
    monkeypatch.setattr(
        auth_service_mod,
        "app_ctx",
        lambda: SimpleNamespace(logger=SimpleNamespace(info=lambda *a, **k: None)),
    )
    with pytest.raises(ValueError):
        auth_service_mod.sync_module_authorization("mod", "bad")
    with pytest.raises(ValueError):
        auth_service_mod.sync_module_authorization("mod", {"assignments": []})
    with pytest.raises(ValueError):
        auth_service_mod.sync_module_authorization(
            "mod", {"assignments": {"role": "bad"}}
        )

    monkeypatch.setattr(
        auth_service_mod,
        "_ensure_permission",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    with pytest.raises(RuntimeError):
        auth_service_mod.sync_module_authorization("mod", {"permissions": ["read"]})
    assert db.rolled_back is True
    assert db.closed is True


def test_seed_admin_user_custom_paths(monkeypatch):
    class _Query:
        def __init__(self, db, model):
            self.db = db
            self.model = model

        def filter(self, _expr):
            return self

        def first(self):
            if self.model is auth_service_mod.Role:
                return self.db.role
            return self.db.user

    class _DB:
        def __init__(self, role=None, user=None, fail=False):
            self.role = role
            self.user = user
            self.fail = fail
            self.added = []
            self.commits = 0
            self.refreshed = 0
            self.rolled = 0
            self.closed = False

        def query(self, model):
            return _Query(self, model)

        def add(self, obj):
            self.added.append(obj)
            if isinstance(obj, auth_service_mod.Role):
                self.role = obj
            if isinstance(obj, auth_service_mod.User):
                self.user = obj

        def commit(self):
            self.commits += 1
            if self.fail:
                raise RuntimeError("db-fail")

        def refresh(self, _obj):
            self.refreshed += 1

        def rollback(self):
            self.rolled += 1

        def close(self):
            self.closed = True

    logger = SimpleNamespace(info=lambda *a, **k: None)
    monkeypatch.setattr(
        auth_service_mod, "app_ctx", lambda: SimpleNamespace(logger=logger)
    )

    db1 = _DB(role=None, user=None)
    monkeypatch.setattr(auth_service_mod, "SessionLocal", lambda: db1)
    auth_service_mod.seed_admin_user_custom("admin", b"pw", "admin@example.com")
    assert db1.commits >= 2
    assert db1.refreshed == 1
    assert db1.user.email == "admin@example.com"
    assert db1.closed is True

    role = SimpleNamespace(name="super", description="x")
    user = SimpleNamespace(
        username="admin",
        email="old@example.com",
        password_hash=b"x",
        access_level=3,
    )
    db2 = _DB(role=role, user=user)
    monkeypatch.setattr(auth_service_mod, "SessionLocal", lambda: db2)
    auth_service_mod.seed_admin_user_custom("admin", b"pw2", "new@example.com")
    assert user.email == "new@example.com"
    assert user.access_level == auth_service_mod.ROLE_LEVEL_SUPER

    db3 = _DB(role=None, user=None, fail=True)
    monkeypatch.setattr(auth_service_mod, "SessionLocal", lambda: db3)
    auth_service_mod.seed_admin_user_custom("admin", b"pw")
    assert db3.rolled >= 1


def test_verify_permissions_profiles_error_and_profiler_paths(monkeypatch):
    class _Perm:
        def __init__(self, name):
            self.name = name

    class _Role:
        def __init__(self, name):
            self.name = name
            self.permissions = [_Perm("p1")]

    user_obj = SimpleNamespace(
        id=1,
        username="u1",
        email="u1@x",
        organization_id=None,
        roles=[_Role("user")],
        access_level=3,
        password_hash=auth_service_mod.get_hashed_password(b"pw"),
    )

    class _Query:
        def __init__(self, user):
            self.user = user

        def filter(self, _expr):
            return self

        def first(self):
            return self.user

    class _DB:
        def __init__(self, user):
            self.user = user

        def query(self, _model):
            return _Query(self.user)

        def close(self):
            return None

    logger = SimpleNamespace(error=lambda *a, **k: None)
    monkeypatch.setattr(
        auth_service_mod, "app_ctx", lambda: SimpleNamespace(logger=logger)
    )
    monkeypatch.setattr(
        auth_service_mod, "current_request_profiler", lambda: _Profiler()
    )
    monkeypatch.setattr(auth_service_mod, "SessionLocal", lambda: _DB(user_obj))

    ok, _user = auth_service_mod.verify_user("u1", b"bad")
    assert ok is False
    assert auth_service_mod.get_user_access_profile_by_username("") is None

    # missing user branch
    monkeypatch.setattr(auth_service_mod, "SessionLocal", lambda: _DB(None))
    assert auth_service_mod.get_user_permissions(1) == []
    assert auth_service_mod.get_user_access_profile(1) is None
    assert auth_service_mod.get_user_access_profile_by_username("u1") is None

    # exception branches
    class _ErrDB:
        def query(self, _m):
            raise RuntimeError("boom")

        def close(self):
            return None

    monkeypatch.setattr(auth_service_mod, "SessionLocal", lambda: _ErrDB())
    assert auth_service_mod.verify_user("u1", b"pw") == (False, None)
    assert auth_service_mod.get_user_permissions(1) == []
    assert auth_service_mod.get_user_access_profile(1) is None
    assert auth_service_mod.get_user_access_profile_by_username("u1") is None
