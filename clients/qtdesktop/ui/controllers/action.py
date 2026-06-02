from __future__ import annotations

import json
import os
import uuid
from typing import Any
from PySide6.QtCore import QTimer

from ..renderers.domains.forms.attachment import upload_attachment_entries
from ..bridge.action_bridge import DesktopActionBridge
from ..messages import HandleUserAction
from ..messages import MessageDispatcher
from ..messages import UserAction
import shiboken6
from ..input_context import collect_action_context, read_input_widget_value
from .log_safety import summarize_log_value


class ActionController:
    """Build and send user action payloads to the backend."""

    def __init__(self, window: Any) -> None:
        """Bind to window-level caches and transport socket."""
        self.window = window
        self._dispatcher = MessageDispatcher()
        self._dispatcher.register("user_action", self._send_user_action)
        self._bridge = DesktopActionBridge(HandleUserAction(self._dispatcher))

    def send_action(
        self, name: str, context: dict, surface_id: str, comp_id: str
    ) -> None:
        """Send one user action merged with current input widget context.

        controller.send_action("submitForm", {"id": "42"}, "main", "submit_btn")
        """
        if name == "client.copy_to_clipboard":
            text = str(context.get("text", ""))
            if text:
                from PySide6.QtGui import QGuiApplication

                clipboard = QGuiApplication.clipboard()
                if clipboard:
                    clipboard.setText(text)
                    title = str(context.get("title", "Copied"))
                    # Show a toast notification if the controller is available
                    notifications = getattr(self.window, "_notifications", None)
                    if notifications:
                        notifications.show_event(
                            {"kind": "toast", "title": title, "text": f"{text}"}
                        )
            return

        if name == "client.next_page":
            current = int(self.window.store.get("/temp/icon_page", 0))
            self.window.store.set("/temp/icon_page", current + 1)
            return

        if name == "client.prev_page":
            current = int(self.window.store.get("/temp/icon_page", 0))
            self.window.store.set("/temp/icon_page", max(0, current - 1))
            return

        if name == "client.reset_page":
            self.window.store.set("/temp/icon_page", 0)
            return

        if name == "client.set_theme":
            raw_checked = context.get("checked")
            if isinstance(raw_checked, bool):
                theme = "light" if raw_checked else "dark"
            else:
                raw_value = context.get("value")
                theme = str(raw_value or "").strip().lower()
                if theme not in {"dark", "light"}:
                    theme = "dark"
            self.window.store.set("/system/client/theme", theme, "global")
            style_controller = getattr(self.window, "_style", None)
            if style_controller is not None:
                style_controller.apply_runtime_stylesheet()
            session = getattr(self.window, "_session", None)
            if session is not None and hasattr(session, "refresh_current_view"):
                session.refresh_current_view(clear_page_scope=False)
            return

        if name == "__stream_binding.subscribe":
            self._send_stream_binding("streamBindingSubscribe", context)
            return

        if name == "__stream_binding.unsubscribe":
            self._send_stream_binding("streamBindingUnsubscribe", context)
            return

        try:
            full_context = self._build_action_context(name, context)
        except Exception as exc:
            self.window._error(f"build_action_context failed: {exc}")
            return
        action = UserAction(
            name=name,
            surface_id=surface_id,
            source_component_id=comp_id,
            context=full_context,
        )
        self._bridge.on_action(action)

        # Trigger reactive notification count refresh for relevant actions
        if name in {"approve_external_access"}:
            notifications = getattr(self.window, "_notifications", None)
            if notifications:
                notifications.refresh_count()

    def _send_user_action(self, action: UserAction) -> None:
        """Translate application action DTO into wire payload and send."""
        request_id = str(uuid.uuid4())
        action_locks = getattr(self.window, "_action_locks", None)
        if action_locks is not None and not action_locks.acquire(
            request_id=request_id,
            action_name=action.name,
        ):
            self.window._debug(
                f"skipping duplicate action while pending: {action.name}"
            )
            return
        msg = {
            "request_id": request_id,
            "jwt": self.window.jwt,
            "session_key": str(getattr(self.window, "session_key", "") or ""),
            "userAction": {
                "name": action.name,
                "surfaceId": action.surface_id,
                "sourceComponentId": action.source_component_id,
                "timestamp": "now",
                "context": action.context,
            },
        }
        try:
            data = (json.dumps(msg, separators=(",", ":")) + "\n").encode("utf-8")
            self.window._debug(f"sending {len(data)} bytes for action {action.name}")
            self.window.client.write(data)
            self.window.client.flush()
        except Exception as e:
            if action_locks is not None:
                action_locks.release(request_id)
            self.window._error(f"send_action failed: {e}")

    def _send_stream_binding(self, key: str, payload: dict | None) -> None:
        msg = {
            "request_id": str(uuid.uuid4()),
            "jwt": self.window.jwt,
            "session_key": str(getattr(self.window, "session_key", "") or ""),
            key: payload if isinstance(payload, dict) else {},
        }
        try:
            data = (json.dumps(msg, separators=(",", ":")) + "\n").encode("utf-8")
            self.window.client.write(data)
            self.window.client.flush()
        except Exception as e:
            self.window._error(f"send_stream_binding failed: {e}")

    def send_binding_action(
        self,
        *,
        request_id: str,
        binding_id: str,
        name: str,
        context: dict[str, Any],
    ) -> None:
        """Send an action used by client-side bound resolvers."""
        msg = {
            "request_id": request_id,
            "jwt": self.window.jwt,
            "session_key": str(getattr(self.window, "session_key", "") or ""),
            "bindingAction": {
                "bindingId": binding_id,
                "name": name,
                "context": context,
            },
        }
        try:
            data = (json.dumps(msg, separators=(",", ":")) + "\n").encode("utf-8")
            self.window._debug(f"sending {len(data)} bytes for binding action {name}")
            self.window.client.write(data)
            self.window.client.flush()
        except Exception as e:
            self.window._error(f"send_binding_action failed: {e}")

    def _collect_action_context(self) -> dict:
        """Collect current values from mounted input widgets."""
        self.window._rebuild_widget_index_from_window()
        return collect_action_context(self.window._input_widgets_cache)

    def _collect_action_context_for_ids(self, input_ids: list[str]) -> dict:
        values: dict[str, Any] = {}
        self.window._rebuild_widget_index_from_window()
        for input_id in input_ids:
            widget = self.window._get_widget_by_id(str(input_id))
            if widget is None:
                continue
            values.update(collect_action_context([widget]))
        return values

    def _collect_uploaded_context_for_ids(
        self,
        input_ids: list[str],
        *,
        module_name: str,
    ) -> dict:
        values: dict[str, Any] = {}
        self.window._rebuild_widget_index_from_window()
        for input_id in input_ids:
            widget = self.window._get_widget_by_id(str(input_id))
            if widget is None:
                print(
                    f"[UPLOAD_DEBUG][desktop.action] widget not found for upload_input_id={input_id}"
                )
                raise RuntimeError(f"upload_input_id not found: {input_id}")
            if not hasattr(widget, "_attachment_state"):
                print(
                    f"[UPLOAD_DEBUG][desktop.action] widget is not attachment input_id={input_id} widget={type(widget).__name__}"
                )
                raise RuntimeError(
                    f"upload_input_id requires Attachment input: {input_id}"
                )
            current_value = read_input_widget_value(widget)
            self.window._debug(
                "[desktop.action] collected attachment "
                f"input_id={input_id} value={summarize_log_value(current_value)}"
            )
            if not isinstance(current_value, list):
                raise RuntimeError(
                    f"upload_input_id requires list attachment value: {input_id}"
                )
            uploaded = upload_attachment_entries(
                current_value,
                module_name=module_name,
                ingest=widget._attachment_state.get("props", {}).get("ingest")
                is not False,
                app_instance=self.window,
            )
            self.window._debug(
                "[desktop.action] uploaded attachment "
                f"input_id={input_id} uploaded={summarize_log_value(uploaded)}"
            )
            if uploaded is None:
                raise RuntimeError(f"attachment upload failed: {input_id}")
            values[str(input_id)] = uploaded
        return values

    def _collect_action_context_for_form(self, form_id: str) -> dict:
        values: dict[str, Any] = {}
        normalized_form_id = str(form_id or "").strip()
        if not normalized_form_id:
            return values

        prefix = f"{normalized_form_id}_"
        self.window._rebuild_widget_index_from_window()
        for widget in self.window._input_widgets_cache:
            if not shiboken6.isValid(widget):
                continue
            key = str(widget.objectName() or "").strip()
            if not key or not key.startswith(prefix):
                continue

            current_value = read_input_widget_value(widget)
            # Keep fully-qualified key for precision/debug
            values[key] = current_value

            # Also expose plain field key for action handlers that expect model names.
            field_key = key[len(prefix) :].strip()
            if field_key and field_key not in values:
                values[field_key] = current_value

        return values

    def _build_action_context(self, action_name: str, context: dict | None) -> dict:
        clean_context, collect_input_ids, upload_input_ids = _extract_client_action_options(context)
        form_id = str(clean_context.get("form_id") or "").strip()

        if collect_input_ids is None:
            if form_id:
                collected = self._collect_action_context_for_form(form_id)
            else:
                collected = self._collect_action_context()
        else:
            collected = self._collect_action_context_for_ids(collect_input_ids)
            if form_id:
                form_values = self._collect_action_context_for_form(form_id)
                # Explicit id collection wins on key collisions.
                collected = {**form_values, **collected}

        if upload_input_ids:
            module_name = _infer_module_name_from_action_name(action_name)
            uploaded = self._collect_uploaded_context_for_ids(
                upload_input_ids,
                module_name=module_name,
            )
            collected = {**collected, **uploaded}

        return {**collected, **clean_context}


def _extract_client_action_options(
    context: dict[str, Any] | None,
) -> tuple[dict[str, Any], list[str] | None, list[str] | None]:
    if not isinstance(context, dict):
        return {}, None, None

    clean_context = dict(context)
    upload_input_ids = _normalize_input_ids(
        clean_context.pop("upload_input_ids", None)
    ) or _normalize_input_ids(clean_context.pop("upload_input_id", None))
    client_meta = clean_context.pop("__client__", None)
    if not isinstance(client_meta, dict):
        return clean_context, None, upload_input_ids

    raw_ids = client_meta.get("collect_input_ids")
    if not isinstance(raw_ids, list):
        return clean_context, None, upload_input_ids
    collect_input_ids = [str(item).strip() for item in raw_ids if str(item).strip()]
    return clean_context, collect_input_ids, upload_input_ids


def _normalize_input_ids(raw: Any) -> list[str] | None:
    if isinstance(raw, list):
        values = [str(item).strip() for item in raw if str(item).strip()]
        return values or None
    single = str(raw or "").strip()
    return [single] if single else None


def _infer_module_name_from_action_name(action_name: str) -> str:
    value = str(action_name or "").strip()
    if "." in value:
        prefix = str(value.split(".", 1)[0] or "").strip()
        if prefix:
            return prefix
    return "core"
