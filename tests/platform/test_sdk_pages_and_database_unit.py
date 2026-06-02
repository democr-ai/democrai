from types import SimpleNamespace

import pytest

import democrai.sdk.pages as pages_mod
import democrai.sdk.database as database_mod


def test_pages_delegate_to_home_resolution(monkeypatch):
    monkeypatch.setattr("democrai.core.application.home.resolve_home_page_path", lambda: "/home")
    monkeypatch.setattr("democrai.core.application.home.resolve_guest_page_path", lambda: "/guest")
    monkeypatch.setattr(
        "democrai.core.application.home.resolve_post_login_redirect_path",
        lambda session: "/org" if session and session.get("organization_id") else "/home",
    )

    sdk = SimpleNamespace(session={"organization_id": 10})
    pages = pages_mod.Pages(sdk)
    assert pages.get_home_path() == "/home"
    assert pages.get_guest_path() == "/guest"
    assert pages.get_post_login_redirect_path() == "/org"
    assert pages.get_post_login_redirect_path({"organization_id": None}) == "/home"


def test_module_data_store_validates_table_prefix(monkeypatch):
    class _Allowed:
        __tablename__ = "p_mod_allowed"

    class _Denied:
        __tablename__ = "users"

    store = database_mod.ModuleDataStore(user_id=1, module_name="mod")
    store._validate_model(_Allowed)
    with pytest.raises(PermissionError):
        store._validate_model(_Denied)

    calls = []
    monkeypatch.setattr(database_mod.DataStore, "add", lambda self, obj: calls.append(("add", obj)) or obj)
    monkeypatch.setattr(database_mod.DataStore, "get", lambda self, model, _id: calls.append(("get", model, _id)) or {"id": _id})
    monkeypatch.setattr(database_mod.DataStore, "list", lambda self, model, **f: calls.append(("list", model, f)) or [])
    monkeypatch.setattr(database_mod.DataStore, "update", lambda self, model, _id, **u: calls.append(("update", model, _id, u)) or {"id": _id})
    monkeypatch.setattr(database_mod.DataStore, "delete", lambda self, model, _id: calls.append(("delete", model, _id)) or True)

    class _AllowedObj:
        __tablename__ = "p_mod_allowed"

    obj = _AllowedObj()
    assert store.add(obj) is obj
    assert store.get(_Allowed, "1") == {"id": "1"}
    assert store.list(_Allowed, x=1) == []
    assert store.update(_Allowed, "1", x=2) == {"id": "1"}
    assert store.delete(_Allowed, "1") is True
    assert [c[0] for c in calls] == ["add", "get", "list", "update", "delete"]


def test_get_module_base_and_database_delegation():
    Base = database_mod.get_module_base("demo")

    class Thing(Base):
        __abstract__ = True

    assert Thing.__tablename__ == "p_demo_thing"

    fake_store = SimpleNamespace(
        add=lambda obj: ("add", obj),
        get=lambda model, _id: ("get", model, _id),
        list=lambda model, **filters: ("list", model, filters),
        update=lambda model, _id, **updates: ("update", model, _id, updates),
        delete=lambda model, _id: ("delete", model, _id),
        extra_attr="x",
    )
    db = database_mod.Database(fake_store, Base)
    marker = object()
    assert db.add(marker) == ("add", marker)
    assert db.get(Thing, "1")[0] == "get"
    assert db.list(Thing, name="n")[0] == "list"
    assert db.update(Thing, "1", name="m")[0] == "update"
    assert db.delete(Thing, "1")[0] == "delete"
    with pytest.raises(AttributeError, match="sdk.database.extra_attr is not exposed"):
        _ = db.extra_attr
