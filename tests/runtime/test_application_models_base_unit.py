from __future__ import annotations

from dataclasses import dataclass

import pytest

from democrai.core.application.auth.roles import ROLE_LEVEL_ORGANIZATION, ROLE_LEVEL_SUPER, ROLE_LEVEL_USER
import democrai.core.application.models.base as base_mod
from democrai.core.application.models.base import BaseCoreModel
from democrai.core.application.models.context import CoreModelContext


class _Expr:
    def __init__(self, op, field, value):
        self.op = op
        self.field = field
        self.value = value


class _Col:
    def __init__(self, name):
        self.name = name

    def __eq__(self, other):
        return _Expr("eq", self.name, other)

    def ilike(self, other):
        return _Expr("ilike", self.name, other)

    def asc(self):
        return _Expr("asc", self.name, None)


class _Model:
    id = _Col("id")
    organization_id = _Col("organization_id")
    user_id = _Col("user_id")
    name = _Col("name")
    status = _Col("status")


class _Query:
    def __init__(self, rows):
        self.rows = list(rows)
        self.filters = []
        self.order = None
        self._offset = 0
        self._limit = None

    def filter(self, expr):
        self.filters.append(expr)
        return self

    def order_by(self, expr):
        self.order = expr
        return self

    def offset(self, value):
        self._offset = value
        return self

    def limit(self, value):
        self._limit = value
        return self

    def all(self):
        rows = self.rows[self._offset :]
        if self._limit is not None:
            rows = rows[: self._limit]
        return rows

    def first(self):
        return self.rows[0] if self.rows else None

    def count(self):
        return len(self.rows)


class _Session:
    def __init__(self, query):
        self.query_obj = query

    def query(self, _model):
        return self.query_obj


class _SessionCM:
    def __init__(self, session):
        self.session = session

    def __call__(self):
        return self

    def __enter__(self):
        return self.session

    def __exit__(self, exc_type, exc, tb):
        return False


@dataclass
class _Row:
    id: int
    name: str


class DemoModel(BaseCoreModel):
    name = "demo"
    sqlalchemy_model = _Model

    def __init__(self, ctx, query):
        super().__init__(ctx)
        self._query = query

    def _session_factory(self):
        return _SessionCM(_Session(self._query))

    def serialize_row(self, item):
        return {"id": item.id, "name": item.name}

    def filters_model(self):
        return [{"field": "name"}, {"field": "status"}]

    def table_model(self):
        return [{"field": "id"}, {"field": "name"}, {"field": "status"}]

    def create(self, payload):
        return payload

    def update(self, entity_id, payload):
        return {"id": entity_id, **payload}

    def delete(self, entity_id):
        return bool(entity_id)


def _ctx(level=ROLE_LEVEL_USER, bypass=False):
    return CoreModelContext(
        user_id=7,
        organization_id=9,
        access_level=level,
        module_name="m",
        session={},
        bypass=bypass,
    )


def test_model_form_defaults_and_filter_normalization():
    q = _Query([_Row(1, "a")])
    model = DemoModel(_ctx(), q)

    assert model.form_model_create() == []
    assert model.form_model_update(1) == []
    assert model.form_model_extra("x") == []
    assert model.filters_model()
    assert model.table_model()

    normalized = model._normalize_filters(
        {
            "name": {"value": " abc "},
            "status": "  ",
            "bad": "x",
            "none": None,
        }
    )
    assert normalized == {"name": "abc"}
    assert model._normalize_filters("bad") == {}


def test_model_access_scope_and_sorting():
    q = _Query([_Row(1, "a")])

    super_model = DemoModel(_ctx(level=ROLE_LEVEL_SUPER), q)
    assert super_model._apply_access_scope(q) is q

    org_model = DemoModel(_ctx(level=ROLE_LEVEL_ORGANIZATION), q)
    org_model._apply_access_scope(q)
    assert any(getattr(expr, "field", "") == "organization_id" for expr in q.filters)

    q2 = _Query([_Row(1, "a")])
    user_model = DemoModel(_ctx(level=ROLE_LEVEL_USER), q2)
    user_model._apply_access_scope(q2)
    assert any(getattr(expr, "field", "") == "user_id" for expr in q2.filters)

    q3 = _Query([_Row(1, "a")])
    bypass_model = DemoModel(_ctx(bypass=True), q3)
    assert bypass_model._apply_access_scope(q3) is q3

    assert user_model._normalize_sort(None) == {"field": "id", "direction": "asc"}
    assert user_model._normalize_sort({"field": "missing", "direction": "desc"}) == {"field": "id", "direction": "asc"}
    assert user_model._normalize_sort({"field": "name", "sortDirection": "DESC"}) == {"field": "name", "direction": "desc"}


def test_model_apply_filters_and_crud_lists():
    rows = [_Row(1, "alpha"), _Row(2, "beta"), _Row(3, "gamma")]
    q = _Query(rows)
    model = DemoModel(_ctx(), q)
    import democrai.core.application.models.base as base_mod

    base_mod.desc = lambda col: _Expr("desc", col.name, None)

    # apply filters covers str ilike + eq
    model._apply_filters(q, {"name": "alp", "status": 1, "missing": "x"})
    ops = {(expr.op, expr.field) for expr in q.filters}
    assert ("ilike", "name") in ops
    assert ("eq", "status") in ops

    # view
    detail = model.view(1)
    assert detail == {"id": 1, "name": "alpha"}

    # count/list/all
    assert model.count(filters={"name": "alpha"}) == 3

    listed = model.list(page=1, page_size=2, filters={"name": "x"}, sort={"field": "name", "direction": "desc"})
    assert listed["page"] == 1
    assert listed["page_size"] == 2
    assert listed["sort"]["field"] == "name"
    assert isinstance(listed["rows"], list)

    model_all = DemoModel(_ctx(), _Query(rows))
    all_rows = model_all.all(filters={"name": "x"}, sort={"field": "id", "direction": "asc"})
    assert all_rows["sort"]["field"] == "id"
    assert len(all_rows["rows"]) == 3


def test_model_sort_fallback_when_field_missing():
    rows = [_Row(1, "a")]
    q = _Query(rows)
    model = DemoModel(_ctx(), q)

    model._apply_sort(q, {"field": "missing", "direction": "desc"})
    assert q.order.field == "id"


def test_model_base_methods_and_not_implemented_branches():
    q = _Query([_Row(1, "x")])
    model = DemoModel(_ctx(), q)

    session = _Session(q)
    assert model.base_query(session) is q
    assert model.serialize_detail(_Row(1, "x")) == {"id": 1, "name": "x"}
    assert model._normalize_sort("bad") == {"field": "id", "direction": "asc"}

    with pytest.raises(NotImplementedError):
        BaseCoreModel.serialize_row(model, object())
    with pytest.raises(NotImplementedError):
        BaseCoreModel.create(model, {})
    with pytest.raises(NotImplementedError):
        BaseCoreModel.update(model, 1, {})
    with pytest.raises(NotImplementedError):
        BaseCoreModel.delete(model, 1)
