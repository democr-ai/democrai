"""
Composite session store.

Identity, UI state, and cache are stored separately:
- identity: minimal user/session identity payload
- ui_state: navigational and workflow state
- cache: transient computed values
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any, Dict, Optional

from democrai.core.infrastructure.session.factory import (
    CACHE_PREFIX,
    IDENTITY_KEYS,
    SessionProviderFactory,
)
from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.runtime.observability.profiling import current_request_profiler


class SessionStore:
    SESSION_META_KEY = "session_meta"

    def __init__(self):
        providers = SessionProviderFactory.create()
        self.identity_store = providers.identity
        self.ui_state_store = providers.ui_state
        self.cache_store = providers.cache
        self._cache: Dict[str, dict] = {}
        self._dirty: set[str] = set()
        self._lock = threading.RLock()

    def _now_ts(self) -> float:
        return time.time()

    def _ensure_meta(self, session: dict, *, now_ts: float | None = None) -> dict:
        now = float(now_ts if now_ts is not None else self._now_ts())
        meta = session.get(self.SESSION_META_KEY)
        if not isinstance(meta, dict):
            meta = {}
        created_at = meta.get("created_at")
        last_accessed_at = meta.get("last_accessed_at")
        if not isinstance(created_at, (int, float)):
            created_at = now
        if not isinstance(last_accessed_at, (int, float)):
            last_accessed_at = now
        session[self.SESSION_META_KEY] = {
            "created_at": float(created_at),
            "last_accessed_at": float(last_accessed_at),
        }
        return session

    def _split(self, session: dict) -> tuple[dict, dict, dict]:
        identity: dict[str, Any] = {}
        ui_state: dict[str, Any] = {}
        cache: dict[str, Any] = {}

        for key, value in session.items():
            if key in IDENTITY_KEYS:
                identity[key] = value
            elif str(key).startswith(CACHE_PREFIX):
                cache[key] = value
            else:
                ui_state[key] = value

        return identity, ui_state, cache

    def _merge(
        self,
        identity: Optional[dict[str, Any]],
        ui_state: Optional[dict[str, Any]],
        cache: Optional[dict[str, Any]],
    ) -> dict:
        merged: dict[str, Any] = {}
        for part in (ui_state, identity, cache):
            if isinstance(part, dict):
                merged.update(part)
        return merged

    def _get_db_session(self):
        ctx = app_ctx()
        db_manager = getattr(ctx, "db", None)
        if db_manager is not None:
            return db_manager.get_session()

        from democrai.core.infrastructure.database import _default_SessionLocal

        return _default_SessionLocal()

    def _load_legacy_session(self, user_key: str) -> Optional[dict]:
        db = self._get_db_session()
        try:
            from democrai.core.infrastructure.database.models import Session

            row = db.query(Session).filter(Session.user_key == user_key).first()
            if not row:
                return None
            if isinstance(row.data, dict):
                raw = row.data
            else:
                raw = json.loads(row.data)
            if isinstance(raw, dict):
                return raw
            return None
        except Exception as e:
            app_ctx().logger.error(
                f"[SessionStore] Error loading legacy session for '{user_key}': {e}"
            )
            return None
        finally:
            db.close()

    def _migrate_legacy_if_needed(self, user_key: str) -> Optional[dict]:
        if getattr(app_ctx(), "setup_mode", False):
            return None
        legacy = self._load_legacy_session(user_key)
        if legacy is None:
            return None
        self._ensure_meta(legacy)
        identity, ui_state, cache = self._split(legacy)
        self.identity_store.save(user_key, identity)
        self.ui_state_store.save(user_key, ui_state)
        self.cache_store.save(user_key, cache)
        return legacy

    def get(self, user_key: str) -> Optional[dict]:
        with self._lock:
            if user_key in self._cache:
                return self._cache[user_key]

            profiler = current_request_profiler()
            try:
                if profiler is not None:
                    with profiler.span("session.identity.load"):
                        identity = self.identity_store.load(user_key)
                    with profiler.span("session.ui_state.load"):
                        ui_state = self.ui_state_store.load(user_key)
                    with profiler.span("session.cache.load"):
                        cache = self.cache_store.load(user_key)
                else:
                    identity = self.identity_store.load(user_key)
                    ui_state = self.ui_state_store.load(user_key)
                    cache = self.cache_store.load(user_key)
                if identity is None and ui_state is None:
                    if profiler is not None:
                        with profiler.span("session.legacy.migrate"):
                            legacy = self._migrate_legacy_if_needed(user_key)
                    else:
                        legacy = self._migrate_legacy_if_needed(user_key)
                    if legacy is None:
                        return None
                    self._ensure_meta(legacy)
                    self._cache[user_key] = legacy
                    return legacy

                if profiler is not None:
                    with profiler.span("session.merge"):
                        session = self._merge(identity, ui_state, cache)
                else:
                    session = self._merge(identity, ui_state, cache)
                self._ensure_meta(session)
                self._cache[user_key] = session
                return session
            except Exception as e:
                app_ctx().logger.error(
                    f"[SessionStore] Error loading session for '{user_key}': {e}"
                )
                return None

    def create(self, user_key: str, data: dict) -> dict:
        with self._lock:
            self._ensure_meta(data)
            self._cache[user_key] = data
            self._dirty.add(user_key)
            return data

    def touch(self, user_key: str, *, now_ts: float | None = None) -> bool:
        with self._lock:
            session = self._cache.get(user_key)
            if session is None:
                return False
            now = float(now_ts if now_ts is not None else self._now_ts())
            self._ensure_meta(session, now_ts=now)
            session[self.SESSION_META_KEY]["last_accessed_at"] = now
            self._dirty.add(user_key)
            return True

    def is_expired(
        self,
        session: dict,
        *,
        idle_ttl_seconds: int | None,
        absolute_ttl_seconds: int | None,
        now_ts: float | None = None,
    ) -> bool:
        if not idle_ttl_seconds and not absolute_ttl_seconds:
            return False
        meta = session.get(self.SESSION_META_KEY)
        if not isinstance(meta, dict):
            return False
        now = float(now_ts if now_ts is not None else self._now_ts())
        created_at = meta.get("created_at")
        last_accessed_at = meta.get("last_accessed_at")
        if absolute_ttl_seconds and isinstance(created_at, (int, float)):
            if (now - float(created_at)) >= int(absolute_ttl_seconds):
                return True
        if idle_ttl_seconds and isinstance(last_accessed_at, (int, float)):
            if (now - float(last_accessed_at)) >= int(idle_ttl_seconds):
                return True
        return False

    def prune_expired(
        self,
        *,
        idle_ttl_seconds: int | None,
        absolute_ttl_seconds: int | None,
        now_ts: float | None = None,
    ) -> list[str]:
        expired_keys: list[str] = []
        candidate_keys = set(self.identity_store.keys()) | set(self.ui_state_store.keys())
        for user_key in candidate_keys:
            session = self.get(user_key)
            if session is None:
                continue
            if self.is_expired(
                session,
                idle_ttl_seconds=idle_ttl_seconds,
                absolute_ttl_seconds=absolute_ttl_seconds,
                now_ts=now_ts,
            ):
                self.delete(user_key)
                expired_keys.append(user_key)
        return expired_keys

    def mark_dirty(self, user_key: str) -> None:
        with self._lock:
            self._dirty.add(user_key)

    def save(self, user_key: str) -> None:
        with self._lock:
            if user_key not in self._cache:
                return

            data = self._cache[user_key]
            profiler = current_request_profiler()
            if profiler is not None:
                with profiler.span("session.split"):
                    identity, ui_state, cache = self._split(data)
            else:
                identity, ui_state, cache = self._split(data)
            try:
                if profiler is not None:
                    with profiler.span("session.identity.save"):
                        self.identity_store.save(user_key, identity)
                    with profiler.span("session.ui_state.save"):
                        self.ui_state_store.save(user_key, ui_state)
                    with profiler.span("session.cache.save"):
                        self.cache_store.save(user_key, cache)
                else:
                    self.identity_store.save(user_key, identity)
                    self.ui_state_store.save(user_key, ui_state)
                    self.cache_store.save(user_key, cache)
                self._dirty.discard(user_key)
            except Exception as e:
                app_ctx().logger.error(
                    f"[SessionStore] Error saving session for '{user_key}': {e}"
                )

    def delete(self, user_key: str) -> None:
        with self._lock:
            self._cache.pop(user_key, None)
            self._dirty.discard(user_key)
            try:
                self.identity_store.delete(user_key)
                self.ui_state_store.delete(user_key)
                self.cache_store.delete(user_key)
            except Exception as e:
                app_ctx().logger.error(
                    f"[SessionStore] Error deleting session for '{user_key}': {e}"
                )

    def save_all(self) -> None:
        with self._lock:
            dirty_keys = list(self._dirty)
        for user_key in dirty_keys:
            self.save(user_key)
