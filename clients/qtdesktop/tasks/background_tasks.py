from __future__ import annotations

from typing import Any, Callable

from ..ui.renderers.base import confirm_action


def _normalize_action_spec(spec: Any) -> dict[str, Any] | None:
    if isinstance(spec, str) and spec.strip():
        return {"name": spec.strip(), "context": {}, "confirm": None}
    if isinstance(spec, dict):
        name = str(spec.get("name") or "").strip()
        if name:
            return {
                "name": name,
                "context": dict(spec.get("context", {}) or {}),
                "confirm": spec.get("confirm"),
            }
    return None


class BackgroundTaskTracker:
    """Track background task status and sync task-confirmation surfaces."""

    def __init__(
        self,
        task_store: dict[str, Any],
        surfaces: dict[str, Any],
        debug: Callable[[str], None],
        warn: Callable[[str], None],
        on_surfaces_changed: Callable[[], None],
        store=None,
    ) -> None:
        """Initialize tracker with shared stores and logging callbacks."""
        self.task_store = task_store
        self.surfaces = surfaces
        self.debug = debug
        self.warn = warn
        self.on_surfaces_changed = on_surfaces_changed
        self.store = store
        self._listeners: dict[str, dict[str, Any]] = {}

    def _store_set(self, task_id: str, key: str, value: Any) -> None:
        if self.store is not None:
            self.store.set(f"background_tasks.{task_id}.{key}", value, "global")

    def register_listener(
        self,
        listener_id: str,
        *,
        task_id: str,
        actions: dict[str, Any],
        send_action: Callable[[str, dict, str, str], None],
        surface_id: str,
        comp_id: str,
    ) -> None:
        normalized_actions: dict[str, dict[str, Any]] = {}
        for key, value in (actions or {}).items():
            spec = _normalize_action_spec(value)
            if spec:
                normalized_actions[key] = spec
        if not normalized_actions:
            self._listeners.pop(listener_id, None)
            return
        self._listeners[listener_id] = {
            "task_id": str(task_id or "").strip(),
            "actions": normalized_actions,
            "send_action": send_action,
            "surface_id": surface_id,
            "comp_id": comp_id,
        }

    def unregister_listener(self, listener_id: str) -> None:
        self._listeners.pop(listener_id, None)

    def _task_snapshot(self, task_id: str) -> dict[str, Any] | None:
        if not task_id:
            return None
        task = self.task_store.get(task_id)
        if isinstance(task, dict):
            return dict(task)
        if self.store is None:
            return None
        stored = self.store.get(f"background_tasks.{task_id}", None, "global")
        return dict(stored) if isinstance(stored, dict) else None

    def _dispatch(self, event_key: str, event_name: str, payload: dict[str, Any]) -> None:
        task_id = str(payload.get("taskId") or payload.get("task_id") or "").strip()
        task = self._task_snapshot(task_id)
        for listener in list(self._listeners.values()):
            action = listener["actions"].get(event_key)
            if not action:
                continue
            listener_task_id = str(listener.get("task_id") or "").strip()
            if task_id and listener_task_id and listener_task_id != task_id:
                continue
            context = {**action.get("context", {}), **payload, "event_name": event_name}
            if task_id and "task_id" not in context:
                context["task_id"] = task_id
            if task is not None and "task" not in context:
                context["task"] = task
            if not confirm_action(None, action.get("confirm")):
                continue
            listener["send_action"](
                action["name"],
                context,
                listener["surface_id"],
                listener["comp_id"],
            )

    def started(self, info: dict) -> None:
        """Record task start metadata."""
        task_id = info.get("taskId")
        self.debug(f"Background task started: {task_id} - {info.get('label')}")
        if task_id:
            self.task_store[task_id] = info
            if self.store is not None:
                self.store.set(f"background_tasks.{task_id}", {
                    "taskId": task_id,
                    "label": info.get("label", ""),
                    "status": "started",
                    "progress": 0,
                }, "global")
        self._dispatch("on_started", "backgroundTaskStarted", dict(info or {}))

    def progress(self, info: dict) -> None:
        """Update task progress/label."""
        task_id = info.get("taskId")
        if task_id in self.task_store:
            self.task_store[task_id]["progress"] = info.get("progress", 0)
            if info.get("label"):
                self.task_store[task_id]["label"] = info["label"]
        self.debug(f"Task {task_id} progress: {info.get('progress', 0):.0%}")
        if task_id:
            self._store_set(task_id, "status", "running")
            self._store_set(task_id, "progress", info.get("progress", 0))
            if info.get("label"):
                self._store_set(task_id, "label", info["label"])
        self._dispatch("on_progress", "backgroundTaskProgress", dict(info or {}))

    def completed(self, info: dict) -> None:
        """Mark task completed and store result payload."""
        task_id = info.get("taskId")
        self.debug(f"Background task completed: {task_id}")
        if task_id in self.task_store:
            self.task_store[task_id]["status"] = "completed"
            self.task_store[task_id]["result"] = info.get("result")
        if task_id:
            self._store_set(task_id, "status", "completed")
            self._store_set(task_id, "progress", 1)
            self._store_set(task_id, "result", info.get("result"))
            if info.get("label"):
                self._store_set(task_id, "label", info["label"])
        payload = dict(info or {})
        self._dispatch("on_completed", "backgroundTaskCompleted", payload)
        self._dispatch("on_finish", "backgroundTaskCompleted", payload)

    def failed(self, info: dict) -> None:
        """Mark task failed and store error details."""
        task_id = info.get("taskId")
        self.warn(f"Background task failed: {task_id} - {info.get('error')}")
        if task_id in self.task_store:
            self.task_store[task_id]["status"] = "failed"
            self.task_store[task_id]["error"] = info.get("error")
        if task_id:
            self._store_set(task_id, "status", "failed")
            self._store_set(task_id, "error", info.get("error"))
            if info.get("label"):
                self._store_set(task_id, "label", info["label"])
        self._dispatch("on_error", "backgroundTaskError", dict(info or {}))

    def confirmation(self, info: dict) -> None:
        """Handle confirmation step by exposing temporary surface components."""
        task_id = info.get("taskId")
        payload = dict(info or {})
        self.debug(f"Background task confirmation requested: {task_id}")
        if task_id in self.task_store:
            self.task_store[task_id]["status"] = "waiting_confirmation"

        surface_id = info.get("surfaceId")
        components = info.get("components", [])
        if not surface_id or not components:
            self._dispatch("on_confirmation", "backgroundTaskConfirmation", payload)
            return

        self.surfaces[surface_id] = {"components": {}}
        for comp in components:
            comp_id = comp.get("id")
            if comp_id:
                self.surfaces[surface_id]["components"][comp_id] = comp
        self.on_surfaces_changed()
        self._dispatch("on_confirmation", "backgroundTaskConfirmation", payload)

    def updated(self, info: dict) -> None:
        """Merge generic task updates and notify listeners."""
        task_id = str(info.get("taskId") or info.get("task_id") or "").strip()
        if task_id:
            current = self.task_store.get(task_id)
            if not isinstance(current, dict):
                current = {"taskId": task_id}
            merged = {**current, **dict(info or {})}
            self.task_store[task_id] = merged
            if self.store is not None:
                self.store.set(f"background_tasks.{task_id}", merged, "global")
        self._dispatch("on_update", "backgroundTaskUpdate", dict(info or {}))

    def event_notification(self, info: dict) -> None:
        """Forward generic event notifications to registered listeners."""
        self._dispatch("on_event_notification", "eventNotification", dict(info or {}))
