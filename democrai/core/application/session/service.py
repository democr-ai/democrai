from __future__ import annotations

import threading
from typing import Any

from democrai.core.application.auth.roles import ROLE_LEVEL_GUEST
from democrai.core.application.auth.service import get_user_access_profile
from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.application.home import resolve_guest_page_path, resolve_home_page_path
from democrai.core.platform.utils.identity import to_optional_int
from democrai.core.runtime.observability.profiling import current_request_profiler


class SessionService:
    """
    Manages the lifecycle, persistence, and expiration of user sessions.

    SessionService provides a high-level API for retrieving or creating sessions,
    persisting changes, and handling identity transitions (e.g., login).
    It also manages a background thread for pruning expired sessions based
    on configured TTL policies.
    """

    def __init__(self, store):
        self.store = store
        self._cleanup_thread: threading.Thread | None = None
        self._cleanup_stop = threading.Event()
        self.idle_ttl_seconds = self._read_positive_int("session.idle_ttl_seconds")
        self.absolute_ttl_seconds = self._read_positive_int(
            "session.absolute_ttl_seconds"
        )
        self.cleanup_interval_seconds = self._read_positive_int(
            "session.cleanup_interval_seconds", default=300
        )

    def _read_positive_int(self, key: str, default: int | None = None) -> int | None:
        cfg = getattr(app_ctx(), "config", None)
        if not cfg:
            return default
        value = cfg.get(key, default)
        if value in (None, "", 0, "0"):
            return None if default is None else default
        try:
            parsed = int(value)
        except Exception:
            return default
        if parsed <= 0:
            return None if default is None else default
        return parsed

    def _is_ttl_enabled(self) -> bool:
        return bool(self.idle_ttl_seconds or self.absolute_ttl_seconds)

    def _expire_if_needed(self, user_key: str, session: dict | None) -> dict | None:
        if session is None or not self._is_ttl_enabled():
            return session
        if not self.store.is_expired(
            session,
            idle_ttl_seconds=self.idle_ttl_seconds,
            absolute_ttl_seconds=self.absolute_ttl_seconds,
        ):
            return session
        self.store.delete(user_key)
        return None

    @staticmethod
    def build_guest_session_user(role: str | None = None) -> dict[str, Any]:
        guest_name = "guest"
        return {
            "username": guest_name,
            "id": guest_name,
            "role": role or "Guest",
            "access_level": ROLE_LEVEL_GUEST,
            "organization_id": None,
            "avatar": "user",
        }

    @staticmethod
    def _storage_key_for_identity(
        user: str | int | None,
        session_key: str | None = None,
    ) -> str:
        if session_key:
            return session_key
        resolved_user_id = to_optional_int(user)
        if resolved_user_id is not None:
            return str(resolved_user_id)
        if user is not None:
            return str(user)
        return "guest"

    @staticmethod
    def _resolve_session_user_identity(
        user: str | int | None,
        role: str | None,
    ) -> tuple[str, dict[str, Any]]:
        if user is None:
            guest_name = "guest"
            return guest_name, SessionService.build_guest_session_user(role)

        resolved_user_id = to_optional_int(user)
        if resolved_user_id is not None:
            profile = get_user_access_profile(resolved_user_id)
            if profile:
                username_value = profile.get("username")
                username = (
                    str(username_value)
                    if username_value is not None and str(username_value)
                    else str(resolved_user_id)
                )
                role_value = profile.get("role")
                resolved_role = (
                    str(role_value)
                    if role_value is not None and str(role_value)
                    else role if role else "Guest"
                )
                language_value = profile.get("language")
                language = (
                    str(language_value)
                    if language_value is not None and str(language_value)
                    else "en"
                )
                return username, {
                    "username": username,
                    "id": resolved_user_id,
                    "role": resolved_role,
                    "access_level": profile.get("access_level", ROLE_LEVEL_GUEST),
                    "organization_id": profile.get("organization_id"),
                    "avatar": "user",
                    "language": language,
                }

        username = str(user)
        return username, {
            "username": username,
            "id": user,
            "role": role or "Guest",
            "access_level": ROLE_LEVEL_GUEST,
            "organization_id": None,
            "avatar": "user",
        }

    def get_or_create(
        self,
        user: str | int | None,
        role: str | None = None,
        *,
        session_key: str | None = None,
    ) -> dict:
        """
        Retrieves an existing session or initializes a new one for a user/guest.

        :param user: The username or ID (optional for guests).
        :param role: The primary role name to assign to a new session.
        :param session_key: An optional persistent key for anonymous sessions.
        :return: The session dictionary.
        """
        user_key = self._storage_key_for_identity(user, session_key)
        profiler = current_request_profiler()
        if profiler is not None:
            with profiler.span("session.store_get"):
                session = self.store.get(user_key)
        else:
            session = self.store.get(user_key)
        session = self._expire_if_needed(user_key, session)
        if session is not None:
            self._sanitize_ephemeral_ui_state(session)
            touch = getattr(self.store, "touch", None)
            if callable(touch):
                touch(user_key)
            return session

        default_path = resolve_home_page_path()
        if app_ctx().setup_mode:
            default_path = "/system/setup"
        elif user is None:
            default_path = resolve_guest_page_path()

        _, session_user = self._resolve_session_user_identity(user, role)
        data = {
            "current_path": default_path,
            "user": session_user,
        }
        if profiler is not None:
            with profiler.span("session.store_create"):
                return self.store.create(user_key, data)
        return self.store.create(user_key, data)

    @staticmethod
    def _sanitize_ephemeral_ui_state(session: dict) -> None:
        """
        UI overlay state must not survive process restarts/session reloads.
        Keep only durable navigation/user data.
        """
        session.pop("pending_modal", None)

    def persist(self, user_key: str) -> None:
        """
        Marks a session as dirty and saves it to the persistent store.

        :param user_key: The unique key identifying the session to persist.
        """
        profiler = current_request_profiler()
        if profiler is not None:
            with profiler.span("session.mark_dirty"):
                self.store.mark_dirty(user_key)
            with profiler.span("session.store_save"):
                self.store.save(user_key)
            return
        self.store.mark_dirty(user_key)
        self.store.save(user_key)

    def persist_identity_change(
        self,
        session: dict,
        request_user: str | None,
        request_session_key: str | None = None,
    ) -> str:
        """
        Handles session migration when a user's identity changes (e.g., login).

        If the new identity differs from the one in the request context, the old
        session is deleted and a new one is created under the new identity key.

        :param session: The current session dictionary (potentially updated with new user data).
        :param request_user: The username/ID from the original request.
        :param request_session_key: The session key from the original request.
        :return: The new user key identifying the session.
        """
        session_user = session.get("user")
        if not isinstance(session_user, dict):
            raise RuntimeError("session_user_required")
        new_user_key = self._storage_key_for_identity(
            session_user.get("id")
            or session_user.get("username")
            or session_user.get("name"),
            request_session_key,
        )
        old_user_key = self._storage_key_for_identity(request_user, request_session_key)
        profiler = current_request_profiler()

        if new_user_key != old_user_key:
            if old_user_key != "guest":
                if profiler is not None:
                    with profiler.span("session.store_delete"):
                        self.store.delete(old_user_key)
                else:
                    self.store.delete(old_user_key)
            if profiler is not None:
                with profiler.span("session.store_create_identity"):
                    self.store.create(new_user_key, session)
            else:
                self.store.create(new_user_key, session)

        return new_user_key

    def cleanup_expired_sessions(self) -> list[str]:
        return self.store.prune_expired(
            idle_ttl_seconds=self.idle_ttl_seconds,
            absolute_ttl_seconds=self.absolute_ttl_seconds,
        )

    def start_cleanup_loop(self) -> None:
        if not self._is_ttl_enabled():
            return
        if not self.cleanup_interval_seconds:
            return
        if self._cleanup_thread and self._cleanup_thread.is_alive():
            return
        self._cleanup_stop.clear()
        self._cleanup_thread = threading.Thread(
            target=self._run_cleanup_loop,
            name="SessionCleanup",
            daemon=True,
        )
        self._cleanup_thread.start()

    def _run_cleanup_loop(self) -> None:
        while not self._cleanup_stop.wait(self.cleanup_interval_seconds):
            try:
                self.cleanup_expired_sessions()
            except Exception as exc:
                app_ctx().logger.error(
                    f"[SessionService] Error pruning expired sessions: {exc}"
                )

    def shutdown(self) -> None:
        self._cleanup_stop.set()
        if self._cleanup_thread and self._cleanup_thread.is_alive():
            self._cleanup_thread.join(timeout=1.0)
        self._cleanup_thread = None
