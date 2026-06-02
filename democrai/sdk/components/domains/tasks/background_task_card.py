from democrai.sdk.components.base import Component


class BackgroundTask(Component):
    """Displays the real-time state of a background task."""

    type = "BackgroundTask"

    def __init__(
        self,
        id: str,
        task_id: str,
        on_finish=None,
        on_started=None,
        on_progress=None,
        on_completed=None,
        on_error=None,
        on_confirmation=None,
        on_update=None,
        on_event_notification=None,
    ):
        super().__init__(id)
        self.set_prop("task_id", task_id)
        if on_finish:
            self.set_prop("on_finish", on_finish)
        if on_started:
            self.set_prop("on_started", on_started)
        if on_progress:
            self.set_prop("on_progress", on_progress)
        if on_completed:
            self.set_prop("on_completed", on_completed)
        if on_error:
            self.set_prop("on_error", on_error)
        if on_confirmation:
            self.set_prop("on_confirmation", on_confirmation)
        if on_update:
            self.set_prop("on_update", on_update)
        if on_event_notification:
            self.set_prop("on_event_notification", on_event_notification)
