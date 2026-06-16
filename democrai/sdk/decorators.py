import inspect
import sys
from functools import wraps
from typing import Any, Callable, Optional

from democrai.core.application.access_policy import AccessManifestRule
from democrai.core.platform.agents.models import PipelineStepDefinition
from democrai.core.platform.agents.registry import (
    agent_registry,
    agent_tool_registry,
    pipeline_registry,
)
from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.runtime.foundation.registry import (
    action_registry,
    guest_page_registry,
    home_page_registry,
    module_command_registry,
    module_event_registry,
    notification_center_view_registry,
    render_hook_registry,
    task_registry,
    template_registry,
)


from .decorator_helpers import commands as _command_decorators
from .decorator_helpers import ai as _ai_decorators
from .decorator_helpers import ui as _ui_decorators
from .decorator_helpers import action as _action_decorators


def _hook_warning(message: str) -> None:
    """Send a render-hook registration warning to the application logger."""
    logger = app_ctx().logger
    if logger is not None:
        logger.warning(message, "hook")


def _event_warning(message: str) -> None:
    """Send an event registration warning to the application logger."""
    logger = app_ctx().logger
    if logger is not None:
        logger.warning(message, "event")


def _get_registry_owner(prefix: str, reg_name: str) -> str:
    """Resolve the owning module name for a fully qualified registry entry."""
    if prefix:
        return prefix
    if isinstance(reg_name, str) and "." in reg_name:
        return reg_name.split(".", 1)[0] or "core"
    return "core"


def _get_module_prefix(func: Callable) -> str:
    """Extract the module prefix used for SDK auto-qualified registrations."""
    module = inspect.getmodule(func)
    module_name = module.__name__ if module else getattr(func, "__module__", "")
    if module_name and module_name.startswith("modules."):
        parts = module_name.split(".")
        if len(parts) >= 2:
            return parts[1]
    return ""


_CTX = sys.modules[__name__]


def action(name: Optional[str] = None):
    """
    Decorator to register a function as a UI action.

    Actions are triggered by client-side events (e.g., button clicks).

    :param name: Optional override for the action name. Defaults to the function name.
    """
    return _action_decorators.action(_CTX, name=name)


def validate(schema: type[Any], *, strip_extra: bool = False):
    """Validate a module action ctx with a Pydantic schema before execution."""
    from democrai.core.application.handler.action_validation import set_action_validation

    def decorator(func: Callable):
        return set_action_validation(func, schema=schema, strip_extra=strip_extra)

    return decorator


def setup_only(func: Callable):
    from democrai.core.application.auth.action import setup_only as _setup_only

    return _setup_only(func)


def allow_public_upload(func: Callable):
    from democrai.core.application.auth.action import (
        allow_public_upload as _allow_public_upload,
    )

    return _allow_public_upload(func)


def callable_command(name: Optional[str] = None):
    """Register a callable module command."""
    return _command_decorators.callable_command(_CTX, name=name)


def scheduled_command(
    name: Optional[str] = None,
    *,
    cron: Optional[str] = None,
    interval_seconds: float | None = None,
):
    """Register a scheduled command triggered by cron or interval seconds."""
    return _command_decorators.scheduled_command(
        _CTX, name=name, cron=cron, interval_seconds=interval_seconds
    )


def long_run_command(name: Optional[str] = None, *, restart_on_exit: bool = True):
    """Register a long-running command that should stay alive after boot."""
    return _command_decorators.long_run_command(
        _CTX, name=name, restart_on_exit=restart_on_exit
    )


def single_run_command(name: Optional[str] = None):
    """Register a boot-time command that runs once and exits."""
    return _command_decorators.single_run_command(_CTX, name=name)


def function(name: Optional[str] = None):
    """Register a plain callable function in the module action/function registry."""
    return _action_decorators.function(_CTX, name=name)


def tool(
    name: Optional[str] = None,
    *,
    title: str = "",
    description: str = "",
    input_schema: Optional[dict[str, Any]] = None,
    confirmation_required: bool = False,
    access: Optional[list[AccessManifestRule]] = None,
    user_selectable: bool = True,
):
    """Register an agent tool exposed to the agent runtime."""
    return _ai_decorators.tool(
        _CTX,
        name=name,
        title=title,
        description=description,
        input_schema=input_schema,
        confirmation_required=confirmation_required,
        access=access,
        user_selectable=user_selectable,
    )


def agent(
    name: Optional[str] = None,
    *,
    title: str = "",
    description: str = "",
    objective: str = "chat",
    system_prompt: str = "",
    tools: Optional[list[str]] = None,
    skills: Optional[list[str]] = None,
    max_iterations: int = 3,
    access: Optional[list[AccessManifestRule]] = None,
    mcp_servers: Optional[list[str]] = None,
    handler: bool = True,
):
    """Register an agent definition."""
    return _ai_decorators.agent(
        _CTX,
        name=name,
        title=title,
        description=description,
        objective=objective,
        system_prompt=system_prompt,
        tools=tools,
        skills=skills,
        max_iterations=max_iterations,
        access=access,
        mcp_servers=mcp_servers,
        handler=handler,
    )


def pipeline(
    name: Optional[str] = None,
    *,
    description: str = "",
    steps: Optional[list[Any]] = None,
    access: Optional[list[AccessManifestRule]] = None,
):
    """Register a pipeline definition composed of tool/agent steps."""
    return _ai_decorators.pipeline(
        _CTX,
        name=name,
        description=description,
        steps=steps,
        access=access,
    )


def get_registry():
    """Return the action registry currently exposed by the SDK."""
    return action_registry


def template(name: str):
    """Mark an async function as a named template coroutine."""
    def decorator(func):
        setattr(func, "_template_name", name)

        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await func(*args, **kwargs)

        return wrapper

    return decorator


def public(func):
    """Mark a callable as public for runtimes that inspect public handlers."""
    setattr(func, "_is_public", True)
    setattr(func, "_public_action", True)
    return func


def only_guest(func):
    """Mark a UI render callable as available only to unauthenticated users."""
    setattr(func, "_only_guest", True)
    return func


def ui_template(name: Optional[str] = None, priority: int = 0):
    """Register a UI template provider."""
    return _ui_decorators.ui_template(_CTX, name=name, priority=priority)


def home_page(path: str, priority: int = 0):
    """Register the authenticated home-page path for a module."""
    def decorator(func):
        home_page_registry.register(path, priority=priority)
        return func

    return decorator


def guest_page(path: str, priority: int = 0):
    """Register the guest landing path for a module."""
    def decorator(func):
        guest_page_registry.register(path, priority=priority)
        return func

    return decorator


def notification_center_view(path: str, priority: int = 0):
    """Register the module route used as the notification center view."""
    def decorator(func):
        prefix = _get_module_prefix(func)
        notification_center_view_registry.register(
            path,
            priority=priority,
            module_name=prefix or "core",
        )
        return func

    return decorator


def render_hook(name: Optional[str] = None, priority: int = 0):
    """Register a render-hook provider."""
    return _ui_decorators.render_hook(_CTX, name=name, priority=priority)


def render_hook_slot(name: str, *, optional: bool = True, description: str = ""):
    """Declare a render-hook slot."""
    return _ui_decorators.render_hook_slot(
        _CTX, name=name, optional=optional, description=description
    )


def event_listener(name: Optional[str] = None, priority: int = 0):
    """Register a module event listener."""
    return _action_decorators.event_listener(_CTX, name=name, priority=priority)


def event_slot(
    name: str,
    *,
    params: Optional[list[str]] = None,
    optional: bool = True,
    description: str = "",
):
    """Declare an event slot that listeners can target."""
    return _action_decorators.event_slot(
        _CTX, name=name, params=params, optional=optional, description=description
    )
