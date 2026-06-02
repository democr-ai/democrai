from __future__ import annotations

from typing import Any, Callable, Optional

from democrai.core.application.access_policy import AccessManifestRule
from democrai.core.platform.utils.normalize import qualify_module_registry_name


def bind_module_decorators(sdk) -> None:
    """Attach module-qualified decorator wrappers onto a decorator facade."""

    def _qualify(name: Optional[str], func: Callable[..., Any]) -> str:
        return qualify_module_registry_name(
            sdk.module_name,
            name,
            fallback_name=func.__name__,
        )

    def _registry_name(name: Optional[str], func: Callable[..., Any]) -> Optional[str]:
        return name if sdk.module_name == "core" else _qualify(name, func)

    def _simple_decorator(base_attr: str):
        base = getattr(sdk, base_attr)

        def scoped(name: Optional[str] = None):
            def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
                return base(_registry_name(name, func))(func)

            return decorator

        return scoped

    def scoped_scheduled_command(
        name: Optional[str] = None,
        *,
        cron: Optional[str] = None,
        interval_seconds: float | None = None,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            return sdk.base_scheduled_command(
                _registry_name(name, func),
                cron=cron,
                interval_seconds=interval_seconds,
            )(func)

        return decorator

    def scoped_long_run_command(
        name: Optional[str] = None,
        *,
        restart_on_exit: bool = True,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            return sdk.base_long_run_command(
                _registry_name(name, func),
                restart_on_exit=restart_on_exit,
            )(func)

        return decorator

    def scoped_tool(
        name: Optional[str] = None,
        *,
        description: str = "",
        input_schema: Optional[dict[str, Any]] = None,
        confirmation_required: bool = False,
        access: Optional[list[AccessManifestRule]] = None,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            return sdk.base_tool(
                _registry_name(name, func),
                description=description,
                input_schema=input_schema,
                confirmation_required=confirmation_required,
                access=access,
            )(func)

        return decorator

    def scoped_agent(
        name: Optional[str] = None,
        *,
        description: str = "",
        objective: str = "chat",
        system_prompt: str = "",
        tools: Optional[list[str]] = None,
        skills: Optional[list[str]] = None,
        max_iterations: int = 3,
        access: Optional[list[AccessManifestRule]] = None,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            return sdk.base_agent(
                _registry_name(name, func),
                description=description,
                objective=objective,
                system_prompt=system_prompt,
                tools=tools,
                skills=skills,
                max_iterations=max_iterations,
                access=access,
            )(func)

        return decorator

    def scoped_pipeline(
        name: Optional[str] = None,
        *,
        description: str = "",
        steps: Optional[list[dict[str, Any]]] = None,
        access: Optional[list[AccessManifestRule]] = None,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            return sdk.base_pipeline(
                _registry_name(name, func),
                description=description,
                steps=steps,
                access=access,
            )(func)

        return decorator

    def scoped_ui_template(name: Optional[str] = None, priority: int = 0):
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            if sdk.module_name == "core" or name is not None:
                return sdk.base_ui_template(name, priority=priority)(func)
            return sdk.base_ui_template(_qualify(None, func), priority=priority)(func)

        return decorator

    def scoped_home_page(path: str, priority: int = 0):
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            return sdk.base_home_page(path, priority=priority)(func)

        return decorator

    def scoped_guest_page(path: str, priority: int = 0):
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            return sdk.base_guest_page(path, priority=priority)(func)

        return decorator

    def scoped_notification_center_view(path: str, priority: int = 0):
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            return sdk.base_notification_center_view(path, priority=priority)(func)

        return decorator

    def scoped_only_guest(func: Callable[..., Any]) -> Callable[..., Any]:
        return sdk.base_only_guest(func)

    def scoped_render_hook(name: Optional[str] = None, priority: int = 0):
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            if sdk.module_name == "core" or name is not None:
                return sdk.base_render_hook(name, priority=priority)(func)
            return sdk.base_render_hook(_qualify(None, func), priority=priority)(func)

        return decorator

    def scoped_render_hook_slot(
        name: str,
        *,
        optional: bool = True,
        description: str = "",
    ):
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            return sdk.base_render_hook_slot(
                name,
                optional=optional,
                description=description,
            )(func)

        return decorator

    def scoped_event_listener(name: Optional[str] = None, priority: int = 0):
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            if sdk.module_name == "core" or name is not None:
                return sdk.base_event_listener(name, priority=priority)(func)
            return sdk.base_event_listener(_qualify(None, func), priority=priority)(func)

        return decorator

    def scoped_event_slot(
        name: str,
        *,
        params: Optional[list[str]] = None,
        optional: bool = True,
        description: str = "",
    ):
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            return sdk.base_event_slot(
                name,
                params=params,
                optional=optional,
                description=description,
            )(func)

        return decorator

    sdk.action = _simple_decorator("base_action")
    sdk.callable_command = _simple_decorator("base_callable_command")
    sdk.scheduled_command = scoped_scheduled_command
    sdk.long_run_command = scoped_long_run_command
    sdk.single_run_command = _simple_decorator("base_single_run_command")
    sdk.function = _simple_decorator("base_function")
    sdk.tool = scoped_tool
    sdk.agent = scoped_agent
    sdk.pipeline = scoped_pipeline
    sdk.ui_template = scoped_ui_template
    sdk.home_page = scoped_home_page
    sdk.guest_page = scoped_guest_page
    sdk.notification_center_view = scoped_notification_center_view
    sdk.only_guest = scoped_only_guest
    sdk.render_hook = scoped_render_hook
    sdk.render_hook_slot = scoped_render_hook_slot
    sdk.event_listener = scoped_event_listener
    sdk.event_slot = scoped_event_slot
