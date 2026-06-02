from __future__ import annotations

import pytest

import democrai.core.application.models.entities.roles as roles_mod
from democrai.core.application.models.context import CoreModelContext


def _ctx() -> CoreModelContext:
    return CoreModelContext(
        user_id=1,
        organization_id=None,
        access_level=1,
        module_name="system",
        session={},
        bypass=False,
    )


class _ContextSession:
    def __init__(self, query_obj):
        self._query_obj = query_obj
        self.committed = 0
        self.deleted = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def query(self, _model):
        return self._query_obj

    def commit(self):
        self.committed += 1

    def delete(self, item):
        self.deleted.append(item)


class _Query:
    def __init__(self, first_result=None, all_result=None):
        self._first_result = first_result
        self._all_result = list(all_result or [])

    def options(self, *args, **kwargs):
        del args, kwargs
        return self

    def filter(self, *args, **kwargs):
        del args, kwargs
        return self

    def order_by(self, *args, **kwargs):
        del args, kwargs
        self._all_result = sorted(
            self._all_result,
            key=lambda item: str(getattr(item, "name", "") or ""),
        )
        return self

    def first(self):
        return self._first_result

    def all(self):
        return list(self._all_result)


def test_roles_model_update_blocks_super_role(monkeypatch):
    model = roles_mod.RolesCoreModel(_ctx())
    super_role = roles_mod.Role(id=1, name="super")
    query = _Query(first_result=super_role)
    session = _ContextSession(query)

    monkeypatch.setattr(model, "base_query", lambda _session: query)
    monkeypatch.setattr(roles_mod, "SessionLocal", lambda: session)

    with pytest.raises(ValueError, match="super role cannot be modified or deleted"):
        model.update(1, {"description": "new"})

    assert session.committed == 0


def test_roles_model_delete_blocks_super_role(monkeypatch):
    model = roles_mod.RolesCoreModel(_ctx())
    super_role = roles_mod.Role(id=1, name="Super")
    query = _Query(first_result=super_role)
    session = _ContextSession(query)

    monkeypatch.setattr(roles_mod, "SessionLocal", lambda: session)

    with pytest.raises(ValueError, match="super role cannot be modified or deleted"):
        model.delete(1)

    assert session.deleted == []
    assert session.committed == 0


def test_roles_model_form_model_extra_returns_sorted_permission_options(monkeypatch):
    model = roles_mod.RolesCoreModel(_ctx())
    permissions = [
        roles_mod.Permission(name="system.user.update"),
        roles_mod.Permission(name="auth.approve_url"),
    ]
    query = _Query(all_result=permissions)
    session = _ContextSession(query)

    monkeypatch.setattr(roles_mod, "SessionLocal", lambda: session)

    options = model.form_model_extra("permissions_options")

    assert options == [
        {"label": "auth.approve_url", "value": "auth.approve_url"},
        {"label": "system.user.update", "value": "system.user.update"},
    ]
    assert model.form_model_extra("unknown") == []
