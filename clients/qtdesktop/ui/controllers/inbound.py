from __future__ import annotations

import heapq
import json
import time
from types import SimpleNamespace
from typing import Any

from ..bridge.inbound_bridge import DesktopInboundBridge
from ..messages import HandleInboundMessage
from ..messages import InboundMessage
from ..messages import MessageDispatcher
from ..window_actions import apply_window_action
from .log_safety import summarize_log_value


class InboundController:
    """Own inbound socket stream parsing and prioritized message draining."""

    def __init__(self, window: Any, session: Any) -> None:
        """Bind queue state, session mutators, and inbound dispatch pipeline."""
        self.window = window
        self.session = session
        self._dispatcher = MessageDispatcher()
        self._bridge = DesktopInboundBridge(
            surface_controller=self.window._surfaces,
            property_controller=self.window._property_updates,
            agent_ui_bridge=getattr(self.window, "_agent_ui", None),
            background_tasks=self.window._background_tasks,
            notification_controller=getattr(self.window, "_notifications", None)
            or SimpleNamespace(show_event=lambda payload: None),
            style_controller=self.window._style,
            window_action_handler=lambda action: apply_window_action(
                self.window, action
            ),
        )
        self._dispatcher.register("surface_update", self._bridge.on_surface_update)
        self._dispatcher.register("begin_rendering", self._bridge.on_begin_rendering)
        self._dispatcher.register("property_update", self._bridge.on_property_update)
        self._dispatcher.register(
            "data_model_update", self._bridge.on_data_model_update
        )
        self._dispatcher.register("delete_surface", self._bridge.on_delete_surface)
        self._dispatcher.register(
            "background_task_started", self._bridge.on_background_task_started
        )
        self._dispatcher.register(
            "background_task_progress", self._bridge.on_background_task_progress
        )
        self._dispatcher.register(
            "background_task_completed", self._bridge.on_background_task_completed
        )
        self._dispatcher.register(
            "background_task_error", self._bridge.on_background_task_error
        )
        self._dispatcher.register(
            "background_task_confirmation",
            self._bridge.on_background_task_confirmation,
        )
        self._dispatcher.register(
            "background_task_update",
            self._bridge.on_background_task_update,
        )
        self._dispatcher.register("state_update", self._bridge.on_state_update)
        self._dispatcher.register("state_patch", self._bridge.on_state_patch)
        self._dispatcher.register("window_action", self._bridge.on_window_action)
        self._dispatcher.register(
            "event_notification", self._bridge.on_event_notification
        )
        self._dispatcher.register(
            "agent_ui_commands", self._bridge.on_agent_ui_commands
        )
        self._dispatcher.register("hot_reload", self._bridge.on_hot_reload)
        self._dispatcher.register(
            "notifications_update", self._handle_notifications_update
        )
        self._dispatcher.register(
            "external_access_approved", self._handle_external_access_approved
        )
        media_controller = getattr(self.window, "_media", None)
        if media_controller is not None:
            self._dispatcher.register("media_resolved", self._handle_media_resolved)
            self._dispatcher.register(
                "media_stream_opened", self._handle_media_stream_opened
            )
            self._dispatcher.register(
                "media_stream_chunk", self._handle_media_stream_chunk
            )
            self._dispatcher.register("media_stream_end", self._handle_media_stream_end)
            self._dispatcher.register(
                "media_stream_error", self._handle_media_stream_error
            )
        bindings = getattr(self.window, "bindings", None)
        if bindings is not None:
            self._dispatcher.register(
                "binding_action_result", bindings.handle_action_result
            )
        self._dispatcher.register("hot_reload", self._bridge.on_hot_reload)
        self._handle_inbound = HandleInboundMessage(self._dispatcher)
        self._rendered_surfaces_by_request: dict[str, set[str]] = {}

    def on_ready_read(self) -> None:
        """Read newline-delimited JSON frames from IPC socket buffer."""
        data = self.window.client.readAll()
        raw = data.data()
        self.window._buf.extend(raw)

        while True:
            nl = self.window._buf.find(b"\n")
            if nl < 0:
                break
            line = self.window._buf[:nl]
            del self.window._buf[: nl + 1]
            if line:
                try:
                    message = line.decode("utf-8")
                    self.on_message(message)
                except Exception as e:
                    self.window._error(f"Error decoding line: {e}")

    def on_message(self, message: str) -> None:
        """Decode one JSON frame and enqueue normalized dict payloads."""
        try:
            payload = json.loads(message)
            if isinstance(payload, list):
                for item in payload:
                    if isinstance(item, dict):
                        self.enqueue(payload=item)
                return
            if isinstance(payload, dict):
                self.enqueue(payload=payload)
        except Exception as e:
            self.window._error(f"Error parsing message: {e}")

    def enqueue(self, payload: dict) -> None:
        """Push message into priority heap and schedule drain tick."""
        priority = self.message_priority(payload)
        self._trace_startup_payload("inbound_enqueue", payload, priority=priority)
        heapq.heappush(
            self.window._inbound_queue,
            (priority, self.window._inbound_seq, payload),
        )
        self.window._inbound_seq += 1
        self.window._inbound_enqueued_total += 1
        self.window._inbound_metrics_window_enqueued += 1
        qdepth = len(self.window._inbound_queue)
        if qdepth > self.window._inbound_max_depth_seen:
            self.window._inbound_max_depth_seen = qdepth
        if qdepth >= self.window._inbound_warn_threshold:
            now = time.monotonic()
            if now - self.window._inbound_last_warn_ts >= 1.0:
                self.window._warn(
                    f"Inbound queue depth high: {qdepth} "
                    f"(threshold={self.window._inbound_warn_threshold})"
                )
                self.window._inbound_last_warn_ts = now
        if not self.window._inbound_drain_timer.isActive():
            self.window._inbound_drain_timer.start()

    def drain(self) -> None:
        """Process up to `max_per_tick` messages to keep UI responsive."""
        processed = 0
        while (
            self.window._inbound_queue and processed < self.window._inbound_max_per_tick
        ):
            _, _, data = heapq.heappop(self.window._inbound_queue)
            self.process_message_data(data)
            processed += 1
            self.window._inbound_processed_total += 1
            self.window._inbound_metrics_window_processed += 1
        self.maybe_log_metrics()
        if self.window._inbound_queue:
            self.window._inbound_drain_timer.start()

    def maybe_log_metrics(self) -> None:
        """Emit periodic queue throughput diagnostics in debug mode."""
        if not self.window.debug_enabled:
            return
        now = time.monotonic()
        elapsed = now - self.window._inbound_metrics_last_ts
        if elapsed < 2.0:
            return
        enq_rate = self.window._inbound_metrics_window_enqueued / elapsed
        proc_rate = self.window._inbound_metrics_window_processed / elapsed
        self.window._debug(
            "InboundQueue "
            f"depth={len(self.window._inbound_queue)} "
            f"max_depth={self.window._inbound_max_depth_seen} "
            f"enq_rate={enq_rate:.1f}/s proc_rate={proc_rate:.1f}/s "
            f"max_per_tick={self.window._inbound_max_per_tick}"
        )
        self.window._inbound_metrics_window_enqueued = 0
        self.window._inbound_metrics_window_processed = 0
        self.window._inbound_metrics_last_ts = now

    def message_priority(self, data: dict) -> int:
        """Assign processing priority for each incoming message kind."""
        if (
            "beginRendering" in data
            or "surfaceUpdate" in data
            or "deleteSurface" in data
            or "dataModelUpdate" in data
            or "stateUpdate" in data
            or "statePatch" in data
            or "state_patch" in data
        ):
            return 0
        if "current_path" in data:
            return 0
        if data.get("type") == "hot_reload":
            return 0
        if data.get("type") in {
            "media_resolved",
            "notifications_update",
            "external_access_approved",
        }:
            return 1
        if data.get("type") in {
            "media_stream_opened",
            "media_stream_chunk",
            "media_stream_end",
            "media_stream_error",
        }:
            return 1
        if "windowAction" in data:
            return 1
        if (
            "backgroundTaskStarted" in data
            or "backgroundTaskProgress" in data
            or "backgroundTaskCompleted" in data
            or "backgroundTaskError" in data
            or "backgroundTaskConfirmation" in data
        ):
            return 1
        update = data.get("propertyUpdate")
        if isinstance(update, dict):
            prop = str(update.get("propertyName", ""))
            action = str(update.get("action", "set"))
            if action == "append" and prop in {"text", "value"}:
                return 3
            if prop == "scroll":
                return 4
            return 2
        return 2

    def process_message_data(self, data: dict) -> None:
        """Apply session side-effects, then dispatch to semantic handlers."""
        self._trace_startup_payload(
            "inbound_process",
            data,
            queue_depth=len(getattr(self.window, "_inbound_queue", [])),
        )
        request_id = str(data.get("request_id") or "").strip()
        touched = (
            self._rendered_surfaces_by_request.setdefault(request_id, set())
            if request_id
            else None
        )
        surface_update = data.get("surfaceUpdate")
        if isinstance(surface_update, dict) and touched is not None:
            surface_id = str(surface_update.get("surfaceId") or "").strip()
            if surface_id:
                touched.add(surface_id)
        begin_rendering = data.get("beginRendering")
        if isinstance(begin_rendering, dict) and touched is not None:
            surface_id = str(begin_rendering.get("surfaceId") or "").strip()
            if surface_id:
                touched.add(surface_id)

        action_locks = getattr(self.window, "_action_locks", None)
        if action_locks is not None:
            action_locks.release(data.get("request_id"))
        self.session.update_identity_from_message(data)
        self.session.update_current_path_from_message(data)

        msg_type = data.get("type")
        if msg_type and msg_type not in {"pong", "ping"}:
            self.window._debug(f"Received message type: {msg_type}")

        client_query = data.get("clientQuery") or data.get("client_query")
        if isinstance(client_query, dict):
            self._handle_client_query(client_query)
            return

        delete_surface = data.get("deleteSurface")
        if isinstance(delete_surface, dict) and touched is not None:
            delete_surface_id = str(delete_surface.get("surfaceId") or "").strip()
            if delete_surface_id and delete_surface_id in touched:
                self.window._debug(
                    "Skipping deleteSurface for surface just rendered in same request: "
                    f"{delete_surface_id} (request_id={request_id})"
                )
                return

        message = self._to_inbound_message(data)
        if message is not None:
            try:
                self._handle_inbound.execute(message)
            except Exception as exc:
                print(
                    f"[DESKTOP_TRACE] dispatch_exception kind={message.kind!r} "
                    f"payload={summarize_log_value(message.payload)!r} error={exc!r}",
                    flush=True,
                )
                import traceback

                traceback.print_exc()
                # don't raise to prevent silent crash
            return

        if touched is not None and len(touched) > 0 and "deleteSurface" in data:
            self._rendered_surfaces_by_request.pop(request_id, None)

        self.window._debug(f"Unhandled inbound payload keys: {list(data.keys())}")

    def _trace_startup_payload(self, event: str, data: dict, **extra: Any) -> None:
        count = int(getattr(self.window, "_startup_trace_inbound_count", 0) or 0)
        if bool(getattr(self.window, "_startup_trace_rendered_main", False)) and count >= 40:
            return
        interesting = (
            "current_path" in data
            or "surfaceUpdate" in data
            or "beginRendering" in data
            or "windowAction" in data
            or "jwt" in data
            or data.get("type") not in {None, "pong", "ping"}
        )
        if not interesting and count >= 20:
            return
        self.window._startup_trace_inbound_count = count + 1
        surface_update = data.get("surfaceUpdate")
        begin_rendering = data.get("beginRendering")
        window_action = data.get("windowAction")
        payload = {
            "keys": list(data.keys()),
            "type": data.get("type"),
            "request_id": data.get("request_id"),
            "current_path": data.get("current_path"),
            "surface_update": (
                surface_update.get("surfaceId") if isinstance(surface_update, dict) else None
            ),
            "begin_rendering": (
                begin_rendering.get("surfaceId") if isinstance(begin_rendering, dict) else None
            ),
            "window_action": (
                window_action.get("op") if isinstance(window_action, dict) else None
            ),
        }
        payload.update(extra)
        self.window._startup_trace(event, **payload)

    def _to_inbound_message(self, data: dict) -> InboundMessage | None:
        """Normalize known desktop protocol payloads into typed inbound messages."""
        key_map = (
            ("surfaceUpdate", "surface_update"),
            ("beginRendering", "begin_rendering"),
            ("propertyUpdate", "property_update"),
            ("dataModelUpdate", "data_model_update"),
            ("deleteSurface", "delete_surface"),
            ("backgroundTaskStarted", "background_task_started"),
            ("backgroundTaskProgress", "background_task_progress"),
            ("backgroundTaskCompleted", "background_task_completed"),
            ("backgroundTaskError", "background_task_error"),
            ("backgroundTaskConfirmation", "background_task_confirmation"),
            ("backgroundTaskUpdate", "background_task_update"),
            ("stateUpdate", "state_update"),
            ("statePatch", "state_patch"),
            ("state_patch", "state_patch"),
            ("windowAction", "window_action"),
            ("eventNotification", "event_notification"),
            ("agentUICommands", "agent_ui_commands"),
            ("bindingActionResult", "binding_action_result"),
            ("notificationsUpdate", "notifications_update"),
            ("externalAccessApproved", "external_access_approved"),
        )

        for key, kind in key_map:
            payload = data.get(key)
            if isinstance(payload, dict):
                return InboundMessage(kind=kind, payload=payload, source="ipc")

        msg_type = data.get("type")
        if msg_type == "hot_reload":
            return InboundMessage(kind="hot_reload", payload={}, source="ipc")
        if msg_type == "media_resolved" and isinstance(data.get("mediaResolved"), dict):
            payload = dict(data["mediaResolved"])
            payload["request_id"] = data.get("request_id")
            return InboundMessage(kind="media_resolved", payload=payload, source="ipc")
        if msg_type == "media_stream_opened" and isinstance(
            data.get("mediaStreamOpened"), dict
        ):
            payload = dict(data["mediaStreamOpened"])
            payload["request_id"] = data.get("request_id")
            return InboundMessage(
                kind="media_stream_opened", payload=payload, source="ipc"
            )
        if msg_type == "media_stream_chunk" and isinstance(
            data.get("mediaStreamChunk"), dict
        ):
            return InboundMessage(
                kind="media_stream_chunk",
                payload=dict(data["mediaStreamChunk"]),
                source="ipc",
            )
        if msg_type == "media_stream_end" and isinstance(
            data.get("mediaStreamEnd"), dict
        ):
            return InboundMessage(
                kind="media_stream_end",
                payload=dict(data["mediaStreamEnd"]),
                source="ipc",
            )
        if msg_type == "media_stream_error" and isinstance(
            data.get("mediaStreamError"), dict
        ):
            payload = dict(data["mediaStreamError"])
            if data.get("request_id") is not None and "request_id" not in payload:
                payload["request_id"] = data.get("request_id")
            return InboundMessage(
                kind="media_stream_error", payload=payload, source="ipc"
            )
        if msg_type == "notifications_update" and isinstance(
            data.get("notificationsUpdate"), dict
        ):
            return InboundMessage(
                kind="notifications_update",
                payload=dict(data["notificationsUpdate"]),
                source="ipc",
            )
        if msg_type == "external_access_approved" and isinstance(
            data.get("externalAccessApproved"), dict
        ):
            return InboundMessage(
                kind="external_access_approved",
                payload=dict(data["externalAccessApproved"]),
                source="ipc",
            )
        return None

    def _handle_client_query(self, query: dict[str, Any]) -> None:
        request_id = str(query.get("requestId") or query.get("request_id") or "").strip()
        if not request_id:
            return
        try:
            value = self._resolve_client_query_value(query)
            payload = {"requestId": request_id, "ok": True, "value": value}
        except Exception as exc:
            payload = {
                "requestId": request_id,
                "ok": False,
                "error": str(exc) or "client_query_failed",
            }
        self._send_client_query_result(payload)

    def _send_client_query_result(self, payload: dict[str, Any]) -> None:
        msg = {"clientQueryResult": payload}
        data = (json.dumps(msg, separators=(",", ":")) + "\n").encode("utf-8")
        self.window.client.write(data)
        self.window.client.flush()

    def _resolve_client_query_value(self, query: dict[str, Any]) -> Any:
        kind = str(query.get("kind") or "").strip()
        surface_id = str(query.get("surfaceId") or query.get("surface_id") or "main")
        path = query.get("path")

        if kind in {"store_value", "current_store_value"}:
            scope = str(query.get("scope") or "auto").strip().lower()
            return self.window.store.get(str(path or "/"), None, scope)

        if kind in {"data_value", "current_data_value"}:
            surface = self.window.surfaces.get(surface_id, {})
            data_model = surface.get("data_model", {}) if isinstance(surface, dict) else {}
            return self._read_path(data_model, path)

        if kind in {"component_props", "current_component_props"}:
            component_id = str(
                query.get("componentId") or query.get("component_id") or ""
            ).strip()
            comp_def = self._find_component(surface_id, component_id)
            return self._component_props(comp_def)

        if kind in {"component", "current_component"}:
            component_id = str(
                query.get("componentId") or query.get("component_id") or ""
            ).strip()
            return self._find_component(surface_id, component_id)

        if kind in {"surface_tree", "current_surface_tree"}:
            return self.window.surfaces.get(surface_id)

        raise ValueError(f"unknown_client_query_kind:{kind}")

    def _find_component(self, surface_id: str, component_id: str) -> dict[str, Any] | None:
        if not component_id:
            return None
        surface = self.window.surfaces.get(surface_id)
        if isinstance(surface, dict):
            component = surface.get("components", {}).get(component_id)
            if isinstance(component, dict):
                return component
        for candidate_surface in self.window.surfaces.values():
            if not isinstance(candidate_surface, dict):
                continue
            component = candidate_surface.get("components", {}).get(component_id)
            if isinstance(component, dict):
                return component
        return None

    @staticmethod
    def _component_props(comp_def: dict[str, Any] | None) -> Any:
        if not isinstance(comp_def, dict):
            return None
        component = comp_def.get("component")
        if not isinstance(component, dict) or not component:
            return None
        comp_type = next(iter(component.keys()))
        return component.get(comp_type)

    @staticmethod
    def _read_path(root: Any, path: Any) -> Any:
        raw = str(path or "").strip()
        if not raw or raw == "/":
            return root
        current = root
        for segment in [part for part in raw.strip("/").replace(".", "/").split("/") if part]:
            if isinstance(current, list) and segment.isdigit():
                index = int(segment)
                if index >= len(current):
                    return None
                current = current[index]
                continue
            if not isinstance(current, dict) or segment not in current:
                return None
            current = current[segment]
        return current

    def _handle_media_resolved(self, payload: dict[str, Any]) -> None:
        media_controller = getattr(self.window, "_media", None)
        if media_controller is None:
            return
        request_id = payload.get("request_id")
        media_payload = dict(payload)
        media_payload.pop("request_id", None)
        media_controller.handle_media_resolved(media_payload, request_id)

    def _handle_media_stream_opened(self, payload: dict[str, Any]) -> None:
        media_controller = getattr(self.window, "_media", None)
        if media_controller is None:
            return
        request_id = payload.get("request_id")
        media_payload = dict(payload)
        media_payload.pop("request_id", None)
        media_controller.handle_media_stream_opened(media_payload, request_id)

    def _handle_media_stream_chunk(self, payload: dict[str, Any]) -> None:
        media_controller = getattr(self.window, "_media", None)
        if media_controller is None:
            return
        media_controller.handle_media_stream_chunk(dict(payload))

    def _handle_media_stream_end(self, payload: dict[str, Any]) -> None:
        media_controller = getattr(self.window, "_media", None)
        if media_controller is None:
            return
        media_controller.handle_media_stream_end(dict(payload))

    def _handle_media_stream_error(self, payload: dict[str, Any]) -> None:
        media_controller = getattr(self.window, "_media", None)
        if media_controller is None:
            return
        media_payload = dict(payload)
        media_payload.pop("request_id", None)
        media_controller.handle_media_stream_error(media_payload)

    def _handle_notifications_update(self, payload: dict[str, Any]) -> None:
        notifications = getattr(self.window, "_notifications", None)
        if notifications is None:
            return
        count = int(payload.get("count") or 0)
        notifications.handle_notifications_update(count)

    def _handle_external_access_approved(self, payload: dict[str, Any]) -> None:
        media_controller = getattr(self.window, "_media", None)
        if media_controller is None:
            return
        module_name = str(payload.get("module_name") or "")
        target = str(payload.get("target") or "")
        media_controller.handle_external_access_approved(module_name, target)
