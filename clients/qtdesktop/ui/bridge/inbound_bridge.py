from __future__ import annotations


class DesktopInboundBridge:
    """Translate inbound application messages to desktop controller calls."""

    def __init__(
        self,
        *,
        surface_controller,
        property_controller,
        agent_ui_bridge,
        background_tasks,
        notification_controller,
        style_controller,
        window_action_handler,
    ) -> None:
        self.surface_controller = surface_controller
        self.property_controller = property_controller
        self.agent_ui_bridge = agent_ui_bridge
        self.background_tasks = background_tasks
        self.notification_controller = notification_controller
        self.style_controller = style_controller
        self.window_action_handler = window_action_handler

    def on_state_update(self, payload: dict) -> None:
        self.surface_controller.handle_state_update(payload)

    def on_state_patch(self, payload: dict) -> None:
        self.surface_controller.handle_state_patch(payload)

    def on_surface_update(self, payload: dict) -> None:
        self.surface_controller.handle_surface_update(payload)

    def on_begin_rendering(self, payload: dict) -> None:
        self.surface_controller.handle_begin_rendering(payload)

    def on_property_update(self, payload: dict) -> None:
        self.property_controller.enqueue(payload)

    def on_data_model_update(self, payload: dict) -> None:
        self.surface_controller.handle_data_model_update(payload)

    def on_delete_surface(self, payload: dict) -> None:
        self.surface_controller.handle_delete_surface(payload)

    def on_background_task_started(self, payload: dict) -> None:
        self.background_tasks.started(payload)

    def on_background_task_progress(self, payload: dict) -> None:
        self.background_tasks.progress(payload)

    def on_background_task_completed(self, payload: dict) -> None:
        self.background_tasks.completed(payload)

    def on_background_task_error(self, payload: dict) -> None:
        self.background_tasks.failed(payload)

    def on_background_task_confirmation(self, payload: dict) -> None:
        self.background_tasks.confirmation(payload)

    def on_background_task_update(self, payload: dict) -> None:
        self.background_tasks.updated(payload)

    def on_window_action(self, payload: dict) -> None:
        self.window_action_handler(payload)

    def on_event_notification(self, payload: dict) -> None:
        self.notification_controller.show_event(payload)

    def on_agent_ui_commands(self, payload: dict) -> None:
        if self.agent_ui_bridge is None:
            return
        commands = payload.get("commands")
        if not isinstance(commands, list):
            return
        self.agent_ui_bridge.apply_commands(commands)

    def on_hot_reload(self, payload: dict | None = None) -> None:
        _ = payload
        self.style_controller.handle_hot_reload()
