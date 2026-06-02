from typing import Any, List, Optional, Type, TypeVar
from sqlalchemy.orm import Query
from sqlalchemy.orm import Session
from .mixins import Base
from democrai.core.application.observability.service import attach_session_audit_actor
from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.application.auth.roles import (
    ROLE_LEVEL_SUPER,
    ROLE_LEVEL_ORGANIZATION,
    ROLE_LEVEL_USER,
)
from democrai.core.platform.utils.identity import to_optional_int, to_required_int

T = TypeVar("T", bound=Base)


class DataStore:
    """
    Core abstraction for interacting with the main data database.
    Enforces scope isolation for all operations.
    """

    def __init__(
        self,
        user_id: int,
        organization_id: Optional[int] = None,
        access_level: int = ROLE_LEVEL_USER,
    ):
        self.user_id = to_required_int(user_id, "user_id")
        self.organization_id = to_optional_int(organization_id)
        self.access_level = access_level

    def _get_session(self) -> Session:
        ctx = app_ctx()
        if ctx and hasattr(ctx, "data_store") and ctx.data_store:
            return ctx.data_store.get_session()
        # Fallback to local SessionLocal if not initialized via app_ctx
        from .database import _get_lazy_session

        return _get_lazy_session()()

    def _attach_actor(self, session: Session) -> None:
        request_ctx = None
        try:
            from democrai.core.runtime.foundation.app import req_ctx

            request_ctx = req_ctx()
        except LookupError:
            request_ctx = None
        attach_session_audit_actor(
            session,
            actor_user_id=self.user_id,
            actor_role=getattr(request_ctx, "role", None),
            organization_id=(
                self.organization_id
                if self.organization_id is not None
                else getattr(request_ctx, "organization_id", None)
            ),
            session_id=getattr(request_ctx, "session_key", None),
            request_id=getattr(request_ctx, "request_id", None),
            correlation_id=getattr(request_ctx, "request_id", None),
            client_ip=getattr(request_ctx, "client_ip", None),
            channel=getattr(request_ctx, "channel", None),
        )

    def add(self, obj: Any) -> Any:
        # Enforce user and optional organization scope on write.
        if hasattr(obj, "user_id"):
            obj.user_id = self.user_id
        if hasattr(obj, "organization_id"):
            obj.organization_id = self.organization_id

        with self._get_session() as session:
            self._attach_actor(session)
            session.add(obj)
            session.commit()
            session.refresh(obj)
            return obj

    def _apply_scope(self, query: Query, model: Type[T]) -> Query:
        if self.access_level == ROLE_LEVEL_SUPER:
            return query

        if (
            self.access_level == ROLE_LEVEL_ORGANIZATION
            and self.organization_id is not None
            and hasattr(model, "organization_id")
        ):
            return query.filter(model.organization_id == self.organization_id)

        if hasattr(model, "user_id"):
            return query.filter(model.user_id == self.user_id)

        return query

    def _scoped_query(self, session: Session, model: Type[T]) -> Query:
        return self._apply_scope(session.query(model), model)

    def get(self, model: Type[T], id: str) -> Optional[T]:
        with self._get_session() as session:
            return self._scoped_query(session, model).filter(model.id == id).first()

    def all(self, model: Type[T], **filters) -> List[T]:
        with self._get_session() as session:
            query = self._scoped_query(session, model)
            for key, value in filters.items():
                if hasattr(model, key):
                    query = query.filter(getattr(model, key) == value)
            return query.all()

    def list(self, model: Type[T], **filters) -> List[T]:
        with self._get_session() as session:
            query = self._scoped_query(session, model)
            for key, value in filters.items():
                if hasattr(model, key):
                    query = query.filter(getattr(model, key) == value)
            return query.all()

    def update(self, model: Type[T], id: str, **updates) -> Optional[T]:
        scoped_updates = dict(updates)
        ignored_ownership_fields = [
            field
            for field in ("user_id", "organization_id")
            if field in scoped_updates and hasattr(model, field)
        ]
        for field in ignored_ownership_fields:
            scoped_updates.pop(field)
        if ignored_ownership_fields:
            ctx = app_ctx()
            logger = getattr(ctx, "logger", None) if ctx is not None else None
            if logger is not None:
                logger.warning(
                    "[DATA DB] Ignoring ownership fields in update for %s id=%s: %s",
                    getattr(model, "__tablename__", model.__name__),
                    id,
                    ", ".join(ignored_ownership_fields),
                )

        with self._get_session() as session:
            self._attach_actor(session)
            obj = self._scoped_query(session, model).filter(model.id == id).first()
            if obj:
                for key, value in scoped_updates.items():
                    setattr(obj, key, value)
                session.commit()
                session.refresh(obj)
            return obj

    def delete(self, model: Type[T], id: str) -> bool:
        with self._get_session() as session:
            self._attach_actor(session)
            obj = self._scoped_query(session, model).filter(model.id == id).first()
            if obj:
                session.delete(obj)
                session.commit()
                return True
            return False
