from typing import Callable, Dict, Optional, Any
from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.platform.agents.registry import agent_registry
from democrai.core.platform.agents.registry import agent_tool_registry
from democrai.core.platform.agents.registry import pipeline_registry
from democrai.core.runtime.foundation.registry_types import (
    CommandLifecycle,
    HomePageRegistration,
    ModuleCommandRegistration,
    ModuleEventDefinition,
    ModuleEventRegistration,
    NotificationCenterViewRegistration,
    RenderHookDefinition,
    RenderHookRegistration,
    TemplateRegistration,
)


class ActionRegistry:
    """
    Central registry for UI actions, commands, and functions.

    Modules register their exposed behavior here to make it discoverable
    by the request cycle engine.
    """

    def __init__(self):
        self.actions: Dict[str, Callable] = {}
        self.commands: Dict[str, Callable] = {}
        self.functions: Dict[str, Callable] = {}

    def register_action(self, name: str, func: Callable):
        self.actions[name] = func

    def register_command(self, name: str, func: Callable):
        self.commands[name] = func

    def register_function(self, name: str, func: Callable):
        self.functions[name] = func

    def get_action(self, name: str) -> Optional[Callable]:
        return self.actions.get(name)

    def get_command(self, name: str) -> Optional[Callable]:
        return self.commands.get(name)

    def get_function(self, name: str) -> Optional[Callable]:
        return self.functions.get(name)


class ModuleCommandRegistry:
    """Registry for module commands grouped by lifecycle semantics."""

    def __init__(self):
        self._commands: Dict[str, ModuleCommandRegistration] = {}
        self._registration_order = 0

    def register(
        self,
        name: str,
        func: Callable,
        *,
        lifecycle: CommandLifecycle,
        module_name: str = "core",
        cron: str | None = None,
        interval_seconds: float | None = None,
        restart_on_exit: bool = False,
    ) -> None:
        resolved_module_name = (
            module_name.strip()
            if isinstance(module_name, str) and module_name.strip()
            else "core"
        )
        handler_module = getattr(func, "__module__", None)
        handler_name = getattr(func, "__name__", None)
        self._commands[name] = ModuleCommandRegistration(
            name=name,
            func=func,
            lifecycle=lifecycle,
            module_name=resolved_module_name,
            order=self._registration_order,
            handler_module=handler_module if isinstance(handler_module, str) else "",
            handler_name=handler_name if isinstance(handler_name, str) else "",
            cron=cron.strip() if isinstance(cron, str) and cron.strip() else None,
            interval_seconds=(
                float(interval_seconds) if interval_seconds is not None else None
            ),
            restart_on_exit=bool(restart_on_exit),
        )
        self._registration_order += 1

    def get(self, name: str) -> Optional[ModuleCommandRegistration]:
        return self._commands.get(name)

    def get_all(
        self,
        *,
        module_name: Optional[str] = None,
        lifecycle: Optional[CommandLifecycle] = None,
    ) -> list[ModuleCommandRegistration]:
        values = list(self._commands.values())
        if module_name is not None:
            values = [cmd for cmd in values if cmd.module_name == module_name]
        if lifecycle is not None:
            values = [cmd for cmd in values if cmd.lifecycle == lifecycle]
        return sorted(values, key=lambda cmd: cmd.order)


class TemplateRegistry:
    """
    Registry for UI templates (shells) that define the app layout.

    Templates are priority-ranked; the highest priority template for a given
    name is used. Templates must contain a '@main_content' anchor.
    """

    def __init__(self):
        self._templates: Dict[str, list[TemplateRegistration]] = {}
        self._registration_order = 0

    def register(self, name: str, func: Callable, priority: int = 0):
        # Validate template: must have exactly one @main_content anchor
        try:
            # Call template with an empty session to inspect components
            components, _ = func(session={})
            found_anchor = False
            component_items = (
                components if isinstance(components, (list, tuple)) else []
            )
            for comp in component_items:
                if not isinstance(comp, dict):
                    continue
                inner = comp.get("component")
                if not isinstance(inner, dict):
                    continue
                # Get the first (and only) key of the component dict
                ctype = list(inner.keys())[0] if inner else None
                props = inner.get(ctype) if ctype else None
                if isinstance(props, dict) and props.get("tag") == "@main_content":
                    if found_anchor:
                        logger = app_ctx().logger
                        if logger:
                            logger.error(f"Template '{name}' has multiple @main_content tags")
                        raise RuntimeError(f"Template '{name}' has multiple @main_content tags")
                    found_anchor = True
            
            if not found_anchor:
                logger = app_ctx().logger
                if logger:
                    logger.error(f"Template '{name}' is missing the required @main_content tag")
                raise RuntimeError(f"Template '{name}' is missing the required @main_content tag")
                
        except Exception as e:
            if isinstance(e, RuntimeError):
                raise
            # If template fails with empty session (e.g. requires specific keys), 
            # we skip structural validation but log a warning.
            logger = app_ctx().logger
            if logger:
                logger.warning(f"Could not structurally validate template '{name}': {e}")

        entries = self._templates.setdefault(name, [])
        entries.append(
            TemplateRegistration(
                name=name,
                func=func,
                priority=int(priority),
                order=self._registration_order,
            )
        )
        self._registration_order += 1
        entries.sort(key=lambda entry: (entry.priority, entry.order), reverse=True)

    def get(self, name: str) -> Optional[Callable]:
        entries = self._templates.get(name, [])
        if not entries:
            return None
        return entries[0].func

    def get_registration(self, name: str) -> Optional[TemplateRegistration]:
        entries = self._templates.get(name, [])
        if not entries:
            return None
        return entries[0]

    def get_all_names(self) -> list:
        return list(self._templates.keys())


class HomePageRegistry:
    """Priority-based registry for the default authenticated home page."""

    def __init__(self):
        self._entries: list[HomePageRegistration] = []
        self._registration_order = 0

    def register(self, path: str, priority: int = 0):
        self._entries.append(
            HomePageRegistration(
                path=path,
                priority=int(priority),
                order=self._registration_order,
            )
        )
        self._registration_order += 1
        self._entries.sort(key=lambda entry: (entry.priority, entry.order), reverse=True)

    def get(self) -> Optional[str]:
        if not self._entries:
            return None
        return self._entries[0].path

    def get_registration(self) -> Optional[HomePageRegistration]:
        if not self._entries:
            return None
        return self._entries[0]


class GuestPageRegistry(HomePageRegistry):
    """Priority-based registry for the default unauthenticated entry page."""


class NotificationCenterViewRegistry:
    """Priority-based registry for the optional notification center route."""

    def __init__(self):
        self._entries: list[NotificationCenterViewRegistration] = []
        self._registration_order = 0

    def register(
        self,
        path: str,
        *,
        priority: int = 0,
        module_name: str = "core",
    ) -> None:
        resolved_path = path.strip() if isinstance(path, str) else ""
        if not resolved_path.startswith("/"):
            raise ValueError("notification_center_view_path_must_be_absolute")
        resolved_module_name = (
            module_name.strip()
            if isinstance(module_name, str) and module_name.strip()
            else "core"
        )
        self._entries.append(
            NotificationCenterViewRegistration(
                path=resolved_path,
                priority=int(priority),
                order=self._registration_order,
                module_name=resolved_module_name,
            )
        )
        self._registration_order += 1
        self._entries.sort(key=lambda entry: (entry.priority, entry.order), reverse=True)

    def get_registration(self) -> Optional[NotificationCenterViewRegistration]:
        if not self._entries:
            return None
        return self._entries[0]

    def get_path(self) -> str:
        registration = self.get_registration()
        return registration.path if registration is not None else ""


class RenderHookRegistry:
    """Priority-based registry for UI render hooks keyed by hook name."""

    def __init__(self):
        self._hooks: Dict[str, list[RenderHookRegistration]] = {}
        self._definitions: Dict[str, RenderHookDefinition] = {}
        self._registration_order = 0

    def register(
        self,
        name: str,
        func: Callable,
        *,
        priority: int = 0,
        module_name: str = "core",
    ):
        resolved_module_name = (
            module_name.strip()
            if isinstance(module_name, str) and module_name.strip()
            else "core"
        )
        entries = self._hooks.setdefault(name, [])
        entries.append(
            RenderHookRegistration(
                name=name,
                func=func,
                priority=int(priority),
                order=self._registration_order,
                module_name=resolved_module_name,
            )
        )
        self._registration_order += 1
        entries.sort(key=lambda entry: (entry.priority, entry.order), reverse=True)

    def declare(
        self,
        name: str,
        *,
        module_name: str = "core",
        optional: bool = True,
        description: str = "",
    ):
        resolved_module_name = (
            module_name.strip()
            if isinstance(module_name, str) and module_name.strip()
            else "core"
        )
        self._definitions[name] = RenderHookDefinition(
            name=name,
            module_name=resolved_module_name,
            optional=bool(optional),
            description=description if isinstance(description, str) else "",
            order=self._registration_order,
        )
        self._registration_order += 1

    def get(self, name: str) -> list[RenderHookRegistration]:
        return list(self._hooks.get(name, []))

    def get_definition(self, name: str) -> Optional[RenderHookDefinition]:
        return self._definitions.get(name)

    def get_definitions(self, module_name: Optional[str] = None) -> list[RenderHookDefinition]:
        definitions = list(self._definitions.values())
        if module_name is None:
            return definitions
        return [
            definition
            for definition in definitions
            if definition.module_name == module_name
        ]


class ModuleEventRegistry:
    """Priority-based registry for module events keyed by event name."""

    def __init__(self):
        self._listeners: Dict[str, list[ModuleEventRegistration]] = {}
        self._definitions: Dict[str, ModuleEventDefinition] = {}
        self._registration_order = 0

    def register(
        self,
        name: str,
        func: Callable,
        *,
        priority: int = 0,
        module_name: str = "core",
    ):
        resolved_module_name = (
            module_name.strip()
            if isinstance(module_name, str) and module_name.strip()
            else "core"
        )
        entries = self._listeners.setdefault(name, [])
        entries.append(
            ModuleEventRegistration(
                name=name,
                func=func,
                priority=int(priority),
                order=self._registration_order,
                module_name=resolved_module_name,
            )
        )
        self._registration_order += 1
        entries.sort(key=lambda entry: (entry.priority, entry.order), reverse=True)

    def declare(
        self,
        name: str,
        *,
        module_name: str = "core",
        params: tuple[str, ...] = (),
        optional: bool = True,
        description: str = "",
    ):
        resolved_module_name = (
            module_name.strip()
            if isinstance(module_name, str) and module_name.strip()
            else "core"
        )
        self._definitions[name] = ModuleEventDefinition(
            name=name,
            module_name=resolved_module_name,
            params=tuple(params),
            optional=bool(optional),
            description=description if isinstance(description, str) else "",
            order=self._registration_order,
        )
        self._registration_order += 1

    def get(self, name: str) -> list[ModuleEventRegistration]:
        return list(self._listeners.get(name, []))

    def get_definition(self, name: str) -> Optional[ModuleEventDefinition]:
        return self._definitions.get(name)

    def get_definitions(self, module_name: Optional[str] = None) -> list[ModuleEventDefinition]:
        definitions = list(self._definitions.values())
        if module_name is None:
            return definitions
        return [
            definition
            for definition in definitions
            if definition.module_name == module_name
        ]


class TaskRegistry:
    """
    Registry for background tasks that can be invoked by name (Serializable Tasks).
    """

    def __init__(self):
        self._tasks: Dict[str, Callable] = {}

    def register(self, name: str, func: Callable):
        self._tasks[name] = func

    def get(self, name: str) -> Optional[Callable]:
        return self._tasks.get(name)

    def get_all(self) -> Dict[str, Callable]:
        return self._tasks.copy()


# Global Singleton Instances
# These are imported by decorators to register items at module load time.
action_registry = ActionRegistry()
task_registry = TaskRegistry()
template_registry = TemplateRegistry()
home_page_registry = HomePageRegistry()
guest_page_registry = GuestPageRegistry()
notification_center_view_registry = NotificationCenterViewRegistry()
render_hook_registry = RenderHookRegistry()
module_event_registry = ModuleEventRegistry()
module_command_registry = ModuleCommandRegistry()


def task(name: str):
    """Decorator to register a background task."""

    def decorator(func: Callable):
        task_registry.register(name, func)
        return func

    return decorator
