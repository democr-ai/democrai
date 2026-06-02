from __future__ import annotations

import functools
import importlib
import inspect
import json
import os
import copy
import re
import threading
from collections import OrderedDict
from contextlib import nullcontext
from typing import Any, Callable, Optional

from democrai.core.infrastructure.modules.manager import resolve_module_resource
from democrai.sdk.components.base import (
    ActionBoundValue,
    Component,
    LiteralValue,
    bound,
)
from democrai.core.platform.ui.media_sources import (
    media_fields_for_component,
    resolve_client_media_source,
)
from democrai.core.platform.utils.conditions import Condition
from democrai.core.platform.utils.discovery import discover_submodules
from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.runtime.observability.profiling import current_request_profiler

__all__ = [
    "Builder",
    "UIComponents",
    "UI",
    "ui",
    "merge_builders",
    "publish_to_stream",
    "ActionBoundValue",
    "LiteralValue",
    "bound",
    "Condition",
    "Component",
    "Router",
]


class UIComponents:
    """Dynamic namespace populated with all public SDK UI component classes."""

    pass


class Router:
    """Lazy router proxy exposed through the SDK UI domain."""

    @staticmethod
    def invalidate_module_routes(module_name: str) -> None:
        from democrai.core.application.routing.router import Router as _Router

        _Router.invalidate_module_routes(module_name)

    @staticmethod
    def _discover_module_patterns(module):
        from democrai.core.application.routing.router import Router as _Router

        return _Router._discover_module_patterns(module)

    @staticmethod
    def _ensure_module_routes(module) -> None:
        from democrai.core.application.routing.router import Router as _Router

        _Router._ensure_module_routes(module)

    @staticmethod
    def parse_path(path: str):
        from democrai.core.application.routing.router import Router as _Router

        return _Router.parse_path(path)

    @staticmethod
    def warmup():
        from democrai.core.application.routing.router import Router as _Router

        return _Router.warmup()

    @staticmethod
    async def resolve(path: str, session: dict, extra_params: Optional[dict] = None):
        from democrai.core.application.routing.router import Router as _Router

        return await _Router.resolve(path, session, extra_params)


async def publish_to_stream(stream_id: str, data: Any):
    """Broadcast arbitrary data to a named runtime stream."""
    network = app_ctx().network
    if network and network.stream_manager:
        await network.stream_manager.broadcast(stream_id, data)


ui = UIComponents()

_YAML_LOAD_CACHE_MAX = 512
_YAML_INCLUDE_PATTERN = re.compile(r"@include/([^\s\"']+)")
_yaml_load_cache: OrderedDict[tuple[Any, ...], Builder] = OrderedDict()
_yaml_load_cache_lock = threading.Lock()

try:
    for module_name in discover_submodules(
        "democrai.sdk.components.domains",
        recursive=True,
    ):
        if ".internal." in module_name:
            continue
        module = importlib.import_module(module_name)
        for attr_name in dir(module):
            component_cls = getattr(module, attr_name)
            if (
                inspect.isclass(component_cls)
                and issubclass(component_cls, Component)
                and component_cls is not Component
            ):
                setattr(ui, attr_name, component_cls)
except Exception as exc:
    app_ctx().logger.error(f"Error discovering SDK components: {exc}")


def merge_builders(base_builder: Any, extra_builder: Any) -> None:
    """Merge transport state and non-duplicate components from one builder into another."""
    if hasattr(base_builder, "merge"):
        base_builder.merge(extra_builder)
    existing_ids = {
        comp.id
        for comp in getattr(base_builder, "_components", [])
        if getattr(comp, "id", None)
    }
    for comp in getattr(extra_builder, "_components", []):
        comp_id = getattr(comp, "id", None)
        if comp_id and comp_id in existing_ids:
            continue
        base_builder.add(comp)
        if comp_id:
            existing_ids.add(comp_id)


class Builder:
    """Fluid API for building and serializing UI component structures."""

    def __init__(self):
        """Create an empty builder for one target surface."""
        self._components: list[Component] = []
        self._data: list[dict[str, Any]] = []
        self._data_model: dict[str, Any] = {}
        self._store_data: dict[str, dict[str, Any]] = {"page": {}, "global": {}}
        self.template: str = "full"
        self.template_dimensions: str = "full"
        self.template_components: list[Any] = []
        self.surface_id: str = "main"
        self.shell_route: Optional[str] = None

    def add(self, component: Component):
        """Add a pre-built component to the builder."""
        self._components.append(component)
        return self

    def get_component(self, component_id: str) -> Optional[Component]:
        """Find a component by id among the builder-managed components."""
        profiler = current_request_profiler()
        with profiler.span("sdk.builder.get_component") if profiler else nullcontext():
            for component in self._components:
                if component.id == component_id:
                    return component
        return None

    def get_roots(self) -> list[Component]:
        """Identify root components not referenced as children by others."""
        profiler = current_request_profiler()
        span = profiler.span("sdk.builder.get_roots") if profiler else nullcontext()
        with span:
            return self._get_roots_impl()

    def _get_roots_impl(self) -> list[Component]:
        """Implementation for root component detection."""

        def _collect_child_ids_from_list(items: Any, target: set[str]) -> None:
            if not isinstance(items, list):
                return
            for item in items:
                if isinstance(item, str):
                    target.add(item)
                    continue
                if hasattr(item, "id"):
                    item_id = getattr(item, "id", None)
                    if isinstance(item_id, str) and item_id:
                        target.add(item_id)
                    _collect_child_ids_from_list(getattr(item, "children", None), target)
                    continue
                if isinstance(item, dict):
                    child_id = item.get("id")
                    if isinstance(child_id, str) and child_id:
                        target.add(child_id)
                    nested_children = item.get("children", {})
                    if (
                        isinstance(nested_children, dict)
                        and "explicitList" in nested_children
                    ):
                        _collect_child_ids_from_list(
                            nested_children["explicitList"], target
                        )

        def _component_payload(component: Any) -> dict[str, Any]:
            payload = getattr(component, "payload", None)
            if isinstance(payload, dict):
                return payload
            props = getattr(component, "props", None)
            children = getattr(component, "children", None)
            if isinstance(props, dict) and isinstance(children, list):
                return {
                    "id": getattr(component, "id", ""),
                    "component": {getattr(component, "type", "Component"): props},
                    "children": {"explicitList": children},
                }
            return component.to_dict()

        all_ids = {
            component.id for component in self._components if component and component.id
        }
        child_ids: set[str] = set()

        for component in self._components:
            data = _component_payload(component)
            children = data.get("children", {})
            if isinstance(children, dict) and "explicitList" in children:
                _collect_child_ids_from_list(children["explicitList"], child_ids)

            component_type = list(data["component"].keys())[0]
            props = data["component"][component_type]

            if "tabs" in props and isinstance(props["tabs"], list):
                for tab in props["tabs"]:
                    if "id" in tab:
                        child_ids.add(tab["id"])
            _collect_child_ids_from_list(props.get("left"), child_ids)
            _collect_child_ids_from_list(props.get("center"), child_ids)
            _collect_child_ids_from_list(props.get("right"), child_ids)

        root_ids = all_ids - child_ids
        return [component for component in self._components if component.id in root_ids]

    def set_data(self, path: str, value: Any):
        """Set a value in the surface data model using slash notation."""
        profiler = current_request_profiler()
        with profiler.span("sdk.builder.set_data") if profiler else nullcontext():
            self._set_nested_value(self._data_model, path, value)
        return self

    def set_store(self, path: str, value: Any, *, scope: str = "page"):
        """Seed page/global client store state using slash notation."""
        scope_key = str(scope or "page").strip().lower()
        if scope_key not in {"page", "global"}:
            raise ValueError(f"Unsupported store scope: {scope}")
        self._set_nested_value(self._store_data[scope_key], path, value)
        return self

    @staticmethod
    def _set_nested_value(target_root: dict[str, Any], path: str, value: Any) -> None:
        keys = [key for key in path.strip("/").split("/") if key]
        target = target_root
        for key in keys[:-1]:
            if key not in target or not isinstance(target[key], dict):
                target[key] = {}
            target = target[key]
        if keys:
            target[keys[-1]] = value

    def set_template(self, name: str, session: Optional[dict] = None):
        """Set the template used to render this surface."""
        profiler = current_request_profiler()
        span = profiler.span("sdk.builder.set_template") if profiler else nullcontext()
        with span:
            return self._set_template_impl(name, session)

    def _set_template_impl(self, name: str, session: Optional[dict] = None):
        """Implementation for template resolution and assignment."""
        self.template = name

        from democrai.core.runtime.foundation.registry import template_registry

        template_fn = template_registry.get(name)
        if not template_fn:
            try:
                import democrai.sdk.templates

                template_fn = template_registry.get(name)
            except ImportError:
                template_fn = None

        if not template_fn:
            template_fn = template_registry.get("full")
            if not template_fn:
                raise RuntimeError(
                    f"Template '{name}' (and 'full' fallback) not found."
                )

        template_components, dimensions = template_fn(session=session)
        self.template_components = template_components
        self.template_dimensions = dimensions
        return self

    def set_surface(self, surface_id: str, *, shell_route: Optional[str] = None):
        """Bind the builder to a surface id and optional shell route."""
        self.surface_id = surface_id
        self.shell_route = shell_route
        return self

    def snapshot(
        self,
        *,
        include_components: bool = True,
        component_serializer: Optional[Callable[[Any], dict[str, Any]]] = None,
    ) -> dict[str, Any]:
        """Serialize the complete builder transport state."""
        profiler = current_request_profiler()
        span = profiler.span("sdk.builder.snapshot") if profiler else nullcontext()
        with span:
            serializer = component_serializer or (lambda component: component.to_dict())
            payload: dict[str, Any] = {
                "data_model": copy.deepcopy(getattr(self, "_data_model", {}) or {}),
                "store_data": copy.deepcopy(
                    getattr(self, "_store_data", {}) or {"page": {}, "global": {}}
                ),
                "template": str(getattr(self, "template", "full") or "full"),
                "template_dimensions": str(
                    getattr(self, "template_dimensions", "full") or "full"
                ),
                "template_components": copy.deepcopy(
                    getattr(self, "template_components", []) or []
                ),
                "surface_id": str(getattr(self, "surface_id", "main") or "main"),
                "shell_route": getattr(self, "shell_route", None),
            }
            if include_components:
                with profiler.span("sdk.builder.snapshot.components") if profiler else nullcontext():
                    payload["components"] = [
                        serializer(component)
                        for component in list(getattr(self, "_components", []) or [])
                    ]
            return payload

    def merge(
        self,
        source: "Builder | dict[str, Any]",
        *,
        components: bool = False,
        metadata: bool = False,
        replace: bool = False,
        component_factory: Optional[Callable[[dict[str, Any]], Any]] = None,
    ):
        """Merge or replace builder transport state from a builder or snapshot."""
        profiler = current_request_profiler()
        with profiler.span("sdk.builder.merge") if profiler else nullcontext():
            return self._merge_impl(
                source,
                components=components,
                metadata=metadata,
                replace=replace,
                component_factory=component_factory,
            )

    def _merge_impl(
        self,
        source: "Builder | dict[str, Any]",
        *,
        components: bool = False,
        metadata: bool = False,
        replace: bool = False,
        component_factory: Optional[Callable[[dict[str, Any]], Any]] = None,
    ):
        source_is_payload = isinstance(source, dict)
        if source_is_payload:
            payload = source
            source_components = list(payload.get("components") or [])
            source_data = payload.get("data_model") or {}
            source_store = payload.get("store_data") or {}
            source_template = payload.get("template")
            source_template_dimensions = payload.get("template_dimensions")
            source_template_components = payload.get("template_components")
            source_surface_id = payload.get("surface_id")
            source_shell_route = payload.get("shell_route")
        else:
            payload = {}
            source_components = list(getattr(source, "_components", []) or [])
            source_data = getattr(source, "_data_model", {}) or {}
            source_store = getattr(source, "_store_data", {}) or {}
            source_template = getattr(source, "template", None)
            source_template_dimensions = getattr(source, "template_dimensions", None)
            source_template_components = getattr(source, "template_components", None)
            source_surface_id = getattr(source, "surface_id", None)
            source_shell_route = getattr(source, "shell_route", None)

        if components:
            next_components = []
            for item in source_components:
                if source_is_payload:
                    if not isinstance(item, dict):
                        continue
                    next_components.append(
                        component_factory(dict(item)) if component_factory else item
                    )
                else:
                    next_components.append(item)
            if replace:
                self._components = next_components
            else:
                self._components.extend(next_components)

        def _merge(dst: dict[str, Any], src: dict[str, Any]) -> None:
            for key, value in src.items():
                if isinstance(value, dict) and isinstance(dst.get(key), dict):
                    _merge(dst[key], value)
                    continue
                dst[key] = copy.deepcopy(value)

        if isinstance(source_data, dict):
            if replace:
                self._data_model = copy.deepcopy(source_data)
            else:
                _merge(self._data_model, source_data)

        if isinstance(source_store, dict):
            if replace:
                self._store_data = {
                    "page": copy.deepcopy(source_store.get("page", {}) or {}),
                    "global": copy.deepcopy(source_store.get("global", {}) or {}),
                }
            else:
                for scope in ("page", "global"):
                    values = source_store.get(scope)
                    if isinstance(values, dict):
                        _merge(self._store_data.setdefault(scope, {}), values)

        if metadata:
            self.template = str(source_template or "full")
            self.template_dimensions = str(source_template_dimensions or "full")
            self.template_components = copy.deepcopy(source_template_components or [])
            self.surface_id = str(source_surface_id or "main")
            self.shell_route = (
                str(source_shell_route)
                if isinstance(source_shell_route, str) and source_shell_route
                else None
            )
        return self

    def build_data_model_update(
        self, surface_id: str = "main", paths: Optional[list[str]] = None
    ) -> str:
        """Build a data model update message."""
        if paths is not None:
            data: dict[str, Any] = {}
            for path in paths:
                keys = [key for key in path.strip("/").split("/") if key]
                value: Any = self._data_model
                for key in keys:
                    if isinstance(value, dict):
                        value = value.get(key)
                    else:
                        value = None
                        break
                data[path] = value
        else:
            data = self._data_model

        return json.dumps(
            self.build_data_model_update_payload(surface_id=surface_id, data=data)
        )

    @staticmethod
    def build_data_model_update_payload(
        surface_id: str = "main",
        *,
        data: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Build the raw dataModelUpdate payload for a surface data snapshot."""
        return {
            "dataModelUpdate": {
                "surfaceId": surface_id,
                "data": data if data is not None else {},
            }
        }

    @staticmethod
    def build_state_update_payload(
        values: dict[str, Any],
        *,
        scope: str = "page",
    ) -> dict[str, Any]:
        """Build the raw stateUpdate payload for client store values."""
        return {"stateUpdate": {"scope": scope, "values": values}}

    @staticmethod
    def build_state_patch_payload(
        path: str,
        action: str,
        value: Any,
        *,
        scope: str = "page",
    ) -> dict[str, Any]:
        """Build the raw statePatch payload for a client store collection."""
        return {
            "statePatch": {
                "scope": scope,
                "path": path,
                "action": action,
                "value": value,
            }
        }

    def build_surface_update_payload(
        self, surface_id: str = "main"
    ) -> list[dict[str, Any]]:
        """Generate the surfaceUpdate protocol messages for all managed components."""
        profiler = current_request_profiler()
        if profiler is None:
            all_components: list[dict[str, Any]] = []
            all_components.extend(self.template_components)
            all_components.extend(
                [component.to_dict() for component in self._components]
            )
        else:
            with profiler.span("ui.surface.components_to_dict"):
                all_components = []
                all_components.extend(self.template_components)
                all_components.extend(
                    [component.to_dict() for component in self._components]
                )

        return [
            {
                "surfaceUpdate": {
                    "surfaceId": surface_id,
                    "components": all_components,
                }
            }
        ]

    def build_surface_update(self, surface_id: str = "main"):
        """Serialize the surface update payload as JSON."""
        payload = self.build_surface_update_payload(surface_id)
        profiler = current_request_profiler()
        if profiler is None:
            return json.dumps(payload)
        with profiler.span("ui.surface.json_dumps"):
            return json.dumps(payload)

    @staticmethod
    def build_delete_surface(surface_id: str) -> str:
        """Build a deleteSurface message to remove a surface from all clients."""
        return json.dumps({"deleteSurface": {"surfaceId": surface_id}})

    @staticmethod
    def build_property_update_payload(
        component_id: str,
        property_name: str,
        value: Any,
        action: str = "set",
        surface_id: str = "main",
    ) -> dict[str, Any]:
        """Build a raw property update payload."""
        return {
            "propertyUpdate": {
                "surfaceId": surface_id,
                "componentId": component_id,
                "propertyName": property_name,
                "action": action,
                "value": value,
            }
        }

    def build_property_update(
        self,
        component_id: str,
        property_name: str,
        value: Any,
        action: str = "set",
        surface_id: str = "main",
    ):
        """Build a delta update for a specific component property."""
        return json.dumps(
            self.build_property_update_payload(
                component_id=component_id,
                property_name=property_name,
                value=value,
                action=action,
                surface_id=surface_id,
            )
        )

    @staticmethod
    def build_collection_append_payload(
        component_id: str,
        property_name: str,
        value: Any,
        *,
        surface_id: str = "main",
    ) -> dict[str, Any]:
        """Build a raw append payload for a collection-like property."""
        return Builder.build_property_update_payload(
            component_id=component_id,
            property_name=property_name,
            value=value,
            action="append",
            surface_id=surface_id,
        )

    @staticmethod
    def build_collection_prepend_payload(
        component_id: str,
        property_name: str,
        value: Any,
        *,
        surface_id: str = "main",
    ) -> dict[str, Any]:
        """Build a raw prepend payload for a collection-like property."""
        return Builder.build_property_update_payload(
            component_id=component_id,
            property_name=property_name,
            value=value,
            action="prepend",
            surface_id=surface_id,
        )

    @staticmethod
    def build_collection_remove_payload(
        component_id: str,
        property_name: str,
        value: Any,
        *,
        surface_id: str = "main",
    ) -> dict[str, Any]:
        """Build a raw remove payload for a collection-like property."""
        return Builder.build_property_update_payload(
            component_id=component_id,
            property_name=property_name,
            value=value,
            action="remove",
            surface_id=surface_id,
        )

    @staticmethod
    def build_collection_replace_payload(
        component_id: str,
        property_name: str,
        value: Any,
        *,
        surface_id: str = "main",
    ) -> dict[str, Any]:
        """Build a raw replace payload for a collection-like property."""
        return Builder.build_property_update_payload(
            component_id=component_id,
            property_name=property_name,
            value=value,
            action="replace",
            surface_id=surface_id,
        )


def _maybe_proxy_external_media_source(
    sdk,
    *,
    component_cls: Callable[..., Any],
    field: str,
    value: str,
) -> str:
    """Proxy supported external media fields through the client-safe media resolver."""
    component_type = str(getattr(component_cls, "type", "") or "")
    if field not in media_fields_for_component(component_type):
        return value
    return resolve_client_media_source(
        module_name=str(sdk.module_name or ""),
        module_path=str(getattr(sdk, "module_path", "") or ""),
        value=str(value or ""),
    )


def _wrap_component(sdk, component_cls: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap a component constructor with SDK-specific resource and action normalization."""

    @functools.wraps(component_cls)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        component_type = str(getattr(component_cls, "type", "") or "")
        media_fields = set(media_fields_for_component(component_type))
        resource_fields = {"icon", "src", "background_image", *media_fields}
        for field in resource_fields:
            if field in kwargs and kwargs[field] and isinstance(kwargs[field], str):
                if field not in media_fields:
                    kwargs[field] = resolve_module_resource(
                        sdk.module_path, kwargs[field]
                    )
                kwargs[field] = _maybe_proxy_external_media_source(
                    sdk,
                    component_cls=component_cls,
                    field=field,
                    value=kwargs[field],
                )

        action_payload = None
        action_params = None
        if "action" in kwargs and isinstance(kwargs["action"], dict):
            action_payload = kwargs.pop("action")
            if isinstance(kwargs.get("params"), dict):
                action_params = dict(kwargs["params"])

        component = component_cls(*args, **kwargs)
        if isinstance(action_payload, dict):
            component.set_prop("action", action_payload)
            if action_params is not None and "params" not in component.props:
                component.set_prop("params", action_params)
        return component

    return wrapper


def _yaml_cache_language(sdk: Any) -> str:
    session = getattr(sdk, "session", None) or {}
    session_language = session.get("user_language")
    if isinstance(session_language, str) and session_language.strip():
        return session_language.strip().lower()
    user = session.get("user") or {}
    user_language = user.get("language") if isinstance(user, dict) else None
    if isinstance(user_language, str) and user_language.strip():
        return user_language.strip().lower()
    return ""


def _resolve_yaml_path(module_path: str, filename: str) -> str:
    path = os.path.join(module_path, filename)
    if not os.path.exists(path):
        for ext in [".yaml", ".yml"]:
            if os.path.exists(path + ext):
                path += ext
                break
    return os.path.normpath(os.path.abspath(path))


def _yaml_file_stat(path: str) -> tuple[str, int, int]:
    stat = os.stat(path)
    return (path, int(stat.st_mtime_ns), int(stat.st_size))


def _yaml_dependency_signature(
    *,
    module_path: str,
    path: str,
    content: str,
    seen: set[str] | None = None,
) -> tuple[tuple[str, int, int], ...]:
    visited = seen if seen is not None else set()
    dependencies = [_yaml_file_stat(path)]
    visited.add(path)
    for match in _YAML_INCLUDE_PATTERN.finditer(content):
        include_path = _resolve_yaml_path(module_path, match.group(1))
        if include_path in visited:
            continue
        with open(include_path, "r", encoding="utf-8") as include_file:
            include_content = include_file.read()
        dependencies.extend(
            _yaml_dependency_signature(
                module_path=module_path,
                path=include_path,
                content=include_content,
                seen=visited,
            )
        )
    return tuple(dependencies)


class UI:
    """Module-facing UI helper domain with wrapped components and YAML helpers."""

    Builder = Builder

    def __init__(self, sdk) -> None:
        """Create the UI facade and bind wrapped component constructors."""
        self.sdk = sdk
        self._bind_components()

    def _bind_components(self) -> None:
        """Attach every public SDK component class as a wrapped constructor."""
        for attr in dir(ui):
            if attr.startswith("_"):
                continue
            component_cls = getattr(ui, attr)
            wrapped_cls = _wrap_component(self.sdk, component_cls)
            setattr(self, attr, wrapped_cls)

    def resolve_route(
        self,
        route: str,
        session: Any,
        extra_params: Optional[dict[str, Any]] = None,
    ):
        """Resolve an application route using the main router."""
        from democrai.core.application.routing import Router

        return Router.resolve(route, session, extra_params=extra_params)

    def resolve_resource(self, resource: str) -> str:
        """Resolve a module-relative static resource path."""
        return resolve_module_resource(self.sdk.module_path, str(resource or ""))

    def resolve_media_source(
        self,
        value: str,
        *,
        component_type: str,
        field: str,
    ) -> str:
        """Resolve and proxy a media source for one component field."""
        raw = self.resolve_resource(value)
        component_stub = type("_MediaComponentStub", (), {"type": component_type})
        return _maybe_proxy_external_media_source(
            self.sdk,
            component_cls=component_stub,
            field=field,
            value=raw,
        )

    def from_yaml(self, yaml_content: str) -> Builder:
        """Build a :class:`Builder` from raw YAML UI content."""
        from democrai.core.platform.ui.yaml_builder import ui_from_yaml

        return ui_from_yaml(yaml_content, sdk=self.sdk)

    def load(self, filename: str) -> Builder:
        """Load a YAML file from the current module path and build its UI."""
        module_path = str(self.sdk.module_path or "")
        path = _resolve_yaml_path(module_path, filename)

        profiler = current_request_profiler()
        with profiler.span("sdk.ui.load.read_file") if profiler else nullcontext():
            with open(path, "r", encoding="utf-8") as file:
                content = file.read()

        cache_key = (
            path,
            _yaml_cache_language(self.sdk),
            _yaml_dependency_signature(
                module_path=module_path,
                path=path,
                content=content,
            ),
        )
        with profiler.span("sdk.ui.load.cache_lookup") if profiler else nullcontext():
            with _yaml_load_cache_lock:
                cached = _yaml_load_cache.get(cache_key)
                if cached is not None:
                    _yaml_load_cache.move_to_end(cache_key)
        if cached is not None:
            if profiler is None:
                return copy.deepcopy(cached)
            with profiler.span("sdk.ui.load.deepcopy"):
                return copy.deepcopy(cached)

        if profiler is None:
            builder = self.from_yaml(content)
        else:
            with profiler.span("sdk.ui.load.from_yaml"):
                builder = self.from_yaml(content)
        with profiler.span("sdk.ui.load.cache_store") if profiler else nullcontext():
            with _yaml_load_cache_lock:
                _yaml_load_cache[cache_key] = builder
                _yaml_load_cache.move_to_end(cache_key)
                while len(_yaml_load_cache) > _YAML_LOAD_CACHE_MAX:
                    _yaml_load_cache.popitem(last=False)
        if profiler is None:
            return copy.deepcopy(builder)
        with profiler.span("sdk.ui.load.deepcopy"):
            return copy.deepcopy(builder)

    def prepare_shell_surface(
        self,
        builder: Builder,
        *,
        surface_id: str,
        shell_route: str,
        content_component_id: str,
        align: str = "top",
    ) -> str:
        """Prepare a shell-mounted surface with an empty content column."""
        builder.set_surface(surface_id, shell_route=shell_route)
        content = self.Column(content_component_id, children=[])
        content.set_property("stretch", True)
        content.set_property("align", align)
        builder.add(content)
        return content_component_id

    def mount_shell_frame(
        self,
        builder: Builder,
        *,
        nav_component_id: str,
        content_surface_id: str,
        root_id: str = "module_root",
        splitter_id: str = "module_split",
        nav_container_id: str = "module_nav_container",
        content_scroll_id: str = "module_content_scroll",
        content_host_id: str = "module_content_host",
        nav_padding: Optional[list[int]] = None,
        nav_spacing: int = 8,
        nav_max_width: int = 340,
        splitter_sizes: Optional[list[int]] = None,
        splitter_max_sizes: Optional[list[int]] = None,
        content_class: str = "container",
    ) -> tuple[str, str]:
        """Build a common shell frame with navigation and content-host areas."""
        row = self.Row(root_id, [splitter_id])
        row.set_property("stretch", True)
        row.set_property("align", "fill")
        row.set_property("height", "100%")
        builder.add(row)

        splitter = self.Splitter(splitter_id, [nav_container_id, content_scroll_id])
        splitter.set_property("stretch", True)
        splitter.set_property("sizes", splitter_sizes or [150, 850])
        splitter.set_property("max_sizes", splitter_max_sizes or [340, 0])
        builder.add(splitter)

        nav_container = self.Column(nav_container_id, [nav_component_id])
        nav_container.set_property("stretch", True)
        nav_container.set_property("height", "100%")
        nav_container.set_property("align", "fill")
        nav_container.set_property("style", "min-height: 100vh;")
        nav_container.set_property("spacing", nav_spacing)
        nav_container.set_property("padding", nav_padding or [18, 16, 18, 16])
        nav_container.set_property("max_width", nav_max_width)
        nav_container.set_property("ui_role", "navigation-container")
        builder.add(nav_container)

        scroll = self.ScrollArea(content_scroll_id, [content_host_id])
        scroll.set_property("stretch", True)
        scroll.set_property("class", content_class)
        builder.add(scroll)

        host = self.SurfaceHost(content_host_id, surface_id=content_surface_id)
        host.set_property("stretch", True)
        host.set_property("ui_role", "content-publisher")
        builder.add(host)

        return root_id, content_host_id

    def nav_active_path_rule(
        self, path: str, active_path: str | None = None
    ) -> dict[str, Any]:
        """Return the conditional rule used to detect active navigation items."""
        if path == f"/{self.sdk.module_name}":
            return {
                "left": {"type": "store", "path": "/current_path", "scope": "global"},
                "op": "==",
                "right": path,
            }

        path = active_path or path

        return {
            "operator": "OR",
            "conditions": [
                {
                    "left": {
                        "type": "store",
                        "path": "/current_path",
                        "scope": "global",
                    },
                    "op": "==",
                    "right": path,
                },
                {
                    "left": {
                        "type": "store",
                        "path": "/current_path",
                        "scope": "global",
                    },
                    "op": "contains",
                    "right": f"{path}/",
                },
            ],
        }
