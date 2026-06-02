from contextlib import contextmanager
from contextvars import ContextVar, Token
import re
from typing import Any, Optional, Type, TypeVar

from sqlalchemy import String, cast, desc
from sqlalchemy.ext.declarative import declared_attr

from democrai.core.infrastructure.storage.data.mixins import UserMixin, Base as CoreBase
from democrai.core.infrastructure.storage.data.store import DataStore

T = TypeVar("T", bound=CoreBase)
_current_module_name: ContextVar[str | None] = ContextVar(
    "sdk_database_current_module_name",
    default=None,
)


_CAMEL_TO_SNAKE_FIRST_PASS_RE = re.compile(r"(.)([A-Z][a-z]+)")
_CAMEL_TO_SNAKE_SECOND_PASS_RE = re.compile(r"([a-z0-9])([A-Z])")


def _camel_to_snake(name: str) -> str:
    """Convert a class-style CamelCase name into snake_case."""
    first_pass = _CAMEL_TO_SNAKE_FIRST_PASS_RE.sub(r"\1_\2", str(name or ""))
    return _CAMEL_TO_SNAKE_SECOND_PASS_RE.sub(r"\1_\2", first_pass).lower()


@contextmanager
def module_database_context(module_name: str):
    """Bind the current module name for module-scoped database declarations."""
    resolved_module_name = str(module_name or "").strip()
    if not resolved_module_name:
        raise ValueError("module_name is required")
    token: Token[str | None] = _current_module_name.set(resolved_module_name)
    try:
        yield
    finally:
        _current_module_name.reset(token)


class ModuleDataStore(DataStore):
    """Module-scoped datastore that only allows access to module-owned tables.

    The datastore guards every CRUD operation by validating that the SQLAlchemy
    model uses the expected module table prefix.
    """

    def __init__(
        self,
        user_id: int,
        module_name: str,
        organization_id: int | None = None,
        access_level: int = 3,
    ):
        """Create a module-scoped datastore with access context information."""
        super().__init__(
            user_id=user_id,
            organization_id=organization_id,
            access_level=access_level,
        )
        self.module_name = module_name
        self.prefix = f"p_{module_name}_"

    def _validate_model(self, model: Type[Any]):
        """Validate that a SQLAlchemy model belongs to the current module."""
        tablename = getattr(model, "__tablename__", "")
        if not tablename.startswith(self.prefix):
            raise PermissionError(
                f"Module {self.module_name} cannot access table {tablename}"
            )

    def add(self, obj: Any) -> Any:
        """Insert an object after validating module table ownership."""
        self._validate_model(type(obj))
        return super().add(obj)

    def get(self, model: Type[T], id: str) -> Optional[T]:
        """Fetch a module-owned row by id."""
        self._validate_model(model)
        return super().get(model, id)

    def all(self, model: Type[T], **filters) -> list[T]:
        """List rows for a module-owned model."""
        self._validate_model(model)
        return super().all(model, **filters)

    def list(self, model: Type[T], **filters) -> list[T]:
        """List rows for a module-owned model."""
        self._validate_model(model)
        return super().list(model, **filters)

    def update(self, model: Type[T], id: str, **updates) -> Optional[T]:
        """Update a row for a module-owned model."""
        self._validate_model(model)
        return super().update(model, id, **updates)

    def delete(self, model: Type[T], id: str) -> bool:
        """Delete a row for a module-owned model."""
        self._validate_model(model)
        return super().delete(model, id)


def get_module_base(module_name: str | None = None):
    """Return a declarative base class whose tables are prefixed per module.

    :param module_name: Optional explicit module name. When omitted, the current
        module-scoped database context is used.
    :return: Declarative base class for module models.
    """
    resolved_module_name = str(module_name or "").strip() or _current_module_name.get()
    if not resolved_module_name:
        raise RuntimeError("module database context is required")

    class ModuleBase(CoreBase, UserMixin):
        __abstract__ = True

        @declared_attr
        def __tablename__(cls):
            return f"p_{resolved_module_name}_{_camel_to_snake(cls.__name__)}"

        @classmethod
        def _module_store(cls) -> ModuleDataStore:
            from democrai.sdk.client import current_sdk

            sdk = current_sdk.get()
            if sdk is None:
                raise RuntimeError("module model methods require an active SDK context")
            return sdk.database._store

        @classmethod
        def _serialize_row(cls, item: Any) -> dict[str, Any]:
            return {
                column.name: getattr(item, column.name)
                for column in cls.__table__.columns
            }

        @classmethod
        def _column_names(cls) -> set[str]:
            return {column.name for column in cls.__table__.columns}

        @classmethod
        def filters_model(cls) -> list[dict[str, Any]]:
            return []

        @classmethod
        def _declared_filter_specs(cls) -> dict[str, dict[str, Any]]:
            specs: dict[str, dict[str, Any]] = {}
            for item in list(cls.filters_model() or []):
                if not isinstance(item, dict):
                    continue
                key = str(
                    item.get("key") or item.get("field") or item.get("column") or ""
                ).strip()
                column = str(item.get("column") or item.get("field") or key).strip()
                operator = str(item.get("operator") or "eq").strip().lower()
                if (
                    not key
                    or not column
                    or column not in cls._column_names()
                    or operator
                    not in {"eq", "ne", "lt", "lte", "gt", "gte", "in", "ilike"}
                ):
                    continue
                specs[key] = {
                    **item,
                    "key": key,
                    "column": column,
                    "operator": operator,
                }
            return specs

        @classmethod
        def _normalize_filters(cls, filters: dict[str, Any] | None) -> dict[str, Any]:
            raw = filters or {}
            if not isinstance(raw, dict):
                return {}
            declared = cls._declared_filter_specs()
            if declared:
                normalized: dict[str, Any] = {}
                for key, spec in declared.items():
                    if key not in raw:
                        continue
                    value = raw[key]
                    if value is None:
                        continue
                    if isinstance(value, dict):
                        value = value.get("value", value.get("q"))
                    if isinstance(value, str):
                        value = value.strip()
                        if value == "":
                            continue
                    normalized[key] = {
                        "column": spec["column"],
                        "operator": spec["operator"],
                        "value": value,
                        "cast": str(spec.get("cast") or "").strip().lower(),
                        "escape": spec.get("escape"),
                    }
                return normalized

            allowed = cls._column_names()
            normalized: dict[str, Any] = {}
            for key, value in raw.items():
                field_name = str(key or "").strip()
                if not field_name or field_name not in allowed:
                    continue
                if value is None:
                    continue
                if isinstance(value, dict):
                    value = value.get("value", value.get("q"))
                if isinstance(value, str):
                    value = value.strip()
                    if value == "":
                        continue
                normalized[field_name] = value
            return normalized

        @classmethod
        def _default_sort(cls) -> dict[str, str]:
            if hasattr(cls, "id"):
                return {"field": "id", "direction": "asc"}
            return {"field": "", "direction": "asc"}

        @classmethod
        def _normalize_sort(cls, sort: dict[str, Any] | None) -> dict[str, str]:
            raw = sort or {}
            if not isinstance(raw, dict):
                raw = {}
            field = str(raw.get("field") or raw.get("sortField") or "").strip()
            direction = (
                str(raw.get("direction") or raw.get("sortDirection") or "")
                .strip()
                .lower()
            )
            if direction not in {"asc", "desc"}:
                direction = "asc"
            if not field or field not in cls._column_names() or not hasattr(cls, field):
                return cls._default_sort()
            return {"field": field, "direction": direction}

        @classmethod
        def _apply_filters(cls, query, filters: dict[str, Any]):
            for field_name, value in filters.items():
                if isinstance(value, dict) and {"column", "operator", "value"}.issubset(
                    value
                ):
                    column_name = str(value.get("column") or "").strip()
                    operator = str(value.get("operator") or "eq").strip().lower()
                    filter_value = value.get("value")
                    cast_type = str(value.get("cast") or "").strip().lower()
                    escape = value.get("escape")
                else:
                    column_name = field_name
                    operator = "ilike" if isinstance(value, str) else "eq"
                    filter_value = value
                    cast_type = ""
                    escape = None

                if not column_name or not hasattr(cls, column_name):
                    continue
                column = getattr(cls, column_name)
                if cast_type == "string":
                    column = cast(column, String)

                if operator == "eq":
                    query = query.filter(column == filter_value)
                elif operator == "ne":
                    query = query.filter(column != filter_value)
                elif operator == "lt":
                    query = query.filter(column < filter_value)
                elif operator == "lte":
                    query = query.filter(column <= filter_value)
                elif operator == "gt":
                    query = query.filter(column > filter_value)
                elif operator == "gte":
                    query = query.filter(column >= filter_value)
                elif operator == "in":
                    values = (
                        list(filter_value or [])
                        if not isinstance(filter_value, str)
                        else [filter_value]
                    )
                    query = query.filter(column.in_(values))
                elif operator == "ilike":
                    pattern = f"%{filter_value}%"
                    if escape:
                        escaped = (
                            str(filter_value)
                            .replace("\\", "\\\\")
                            .replace("%", "\\%")
                            .replace("_", "\\_")
                        )
                        pattern = f"%{escaped}%"
                        query = query.filter(column.ilike(pattern, escape=str(escape)))
                    else:
                        query = query.filter(column.ilike(pattern))
            return query

        @classmethod
        def _apply_sort(cls, query, sort: dict[str, str]):
            field = str(sort.get("field") or "").strip()
            if not field or not hasattr(cls, field):
                return query
            column = getattr(cls, field)
            if str(sort.get("direction") or "").strip().lower() == "desc":
                return query.order_by(desc(column))
            return query.order_by(column.asc())

        @classmethod
        def view(cls, entity_id: int | str) -> dict[str, Any] | None:
            store = cls._module_store()
            store._validate_model(cls)
            with store._get_session() as session:
                item = (
                    store._scoped_query(session, cls)
                    .filter(cls.id == entity_id)
                    .first()
                )
                if item is None:
                    return None
                return cls._serialize_row(item)

        @classmethod
        def count(cls, *, filters: dict[str, Any] | None = None) -> int:
            store = cls._module_store()
            store._validate_model(cls)
            normalized_filters = cls._normalize_filters(filters)
            with store._get_session() as session:
                query = store._scoped_query(session, cls)
                query = cls._apply_filters(query, normalized_filters)
                return int(query.count())

        @classmethod
        def list(
            cls,
            *,
            page: int = 0,
            page_size: int = 25,
            filters: dict[str, Any] | None = None,
            sort: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            store = cls._module_store()
            store._validate_model(cls)
            resolved_page = max(0, int(page or 0))
            resolved_page_size = max(1, min(int(page_size or 25), 200))
            normalized_filters = cls._normalize_filters(filters)
            normalized_sort = cls._normalize_sort(sort)

            with store._get_session() as session:
                query = store._scoped_query(session, cls)
                query = cls._apply_filters(query, normalized_filters)
                total_rows = int(query.count())
                rows = (
                    cls._apply_sort(query, normalized_sort)
                    .offset(resolved_page * resolved_page_size)
                    .limit(resolved_page_size)
                    .all()
                )

            return {
                "rows": [cls._serialize_row(item) for item in rows],
                "total_rows": total_rows,
                "page": resolved_page,
                "page_size": resolved_page_size,
                "filters": normalized_filters,
                "sort": normalized_sort,
            }

        @classmethod
        def all(
            cls,
            *,
            filters: dict[str, Any] | None = None,
            sort: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            store = cls._module_store()
            store._validate_model(cls)
            normalized_filters = cls._normalize_filters(filters)
            normalized_sort = cls._normalize_sort(sort)

            with store._get_session() as session:
                query = store._scoped_query(session, cls)
                query = cls._apply_filters(query, normalized_filters)
                rows = cls._apply_sort(query, normalized_sort).all()

            return {
                "rows": [cls._serialize_row(item) for item in rows],
                "filters": normalized_filters,
                "sort": normalized_sort,
            }

    return ModuleBase


class Database:
    """Module-facing database domain with CRUD operations and model base."""

    def __init__(self, store: ModuleDataStore, base: type[CoreBase]) -> None:
        """Bind the public database facade to one module-scoped datastore."""
        self._store = store
        self.Base = base

    def add(self, obj: Any) -> Any:
        """Insert an object after validating module table ownership."""
        return self._store.add(obj)

    def get(self, model: Type[T], id: str) -> Optional[T]:
        """Fetch a module-owned row by id."""
        return self._store.get(model, id)

    def all(self, model: Type[T], **filters):
        """List rows for a module-owned model."""
        return self._store.all(model, **filters)

    def list(self, model: Type[T], **filters):
        """List rows for a module-owned model."""
        return self._store.list(model, **filters)

    def update(self, model: Type[T], id: str, **updates) -> Optional[T]:
        """Update a row for a module-owned model."""
        return self._store.update(model, id, **updates)

    def delete(self, model: Type[T], id: str) -> bool:
        """Delete a row for a module-owned model."""
        return self._store.delete(model, id)

    def __getattr__(self, item: str) -> Any:
        raise AttributeError(
            f"sdk.database.{item} is not exposed; use the public database "
            "methods or module model methods instead"
        )
