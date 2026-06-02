from __future__ import annotations

import json

from democrai.core.runtime.foundation.app import app_ctx


class SqlAlchemyJsonStore:
    def __init__(self, model: type) -> None:
        self.model = model

    def _get_db_session(self):
        ctx = app_ctx()
        if ctx.db:
            return ctx.db.get_session()

        from democrai.core.infrastructure.database import _default_SessionLocal

        return _default_SessionLocal()

    def load(self, key: str) -> dict[str, object] | None:
        db = self._get_db_session()
        try:
            row = db.query(self.model).filter(self.model.session_key == key).first()
            if not row:
                return None
            raw = json.loads(row.data)
            return raw if isinstance(raw, dict) else None
        finally:
            db.close()

    def save(self, key: str, value: dict[str, object]) -> None:
        db = self._get_db_session()
        try:
            row = db.query(self.model).filter(self.model.session_key == key).first()
            serialized = json.dumps(value, default=str)
            if row:
                row.data = serialized
            else:
                row = self.model(session_key=key, data=serialized)
                db.add(row)
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def delete(self, key: str) -> None:
        db = self._get_db_session()
        try:
            db.query(self.model).filter(self.model.session_key == key).delete()
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def keys(self) -> list[str]:
        db = self._get_db_session()
        try:
            rows = db.query(self.model.session_key).all()
            return [str(row[0]) for row in rows]
        finally:
            db.close()
