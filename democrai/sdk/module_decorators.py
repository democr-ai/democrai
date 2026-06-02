from __future__ import annotations

BASE_DECORATORS = (
    "action",
    "callable_command",
    "scheduled_command",
    "long_run_command",
    "single_run_command",
    "function",
    "tool",
    "agent",
    "pipeline",
    "ui_template",
    "home_page",
    "guest_page",
    "notification_center_view",
    "only_guest",
    "render_hook",
    "render_hook_slot",
    "event_listener",
    "event_slot",
)


class Decorators:
    """Module-scoped wrapper around the global decorator registration surface."""

    def __init__(self, sdk) -> None:
        """Bind decorator helpers to the current module name."""
        self.module_name = sdk.module_name

        import democrai.sdk.decorators as decorators

        for name in BASE_DECORATORS:
            setattr(self, f"base_{name}", getattr(decorators, name))

        from democrai.sdk.decorator_binding import bind_module_decorators

        bind_module_decorators(self)

        from democrai.core.runtime.foundation.registry import task

        self.task = task
        self.public = decorators.public
        self.template = decorators.template
