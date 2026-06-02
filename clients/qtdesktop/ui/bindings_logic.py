from __future__ import annotations

import hashlib
from typing import Any


def normalize_spec(
    value: Any,
    bound_spec_cls: type,
    *,
    allow_implicit_path: bool = True,
) -> Any:
    if not isinstance(value, dict):
        return None

    kind = value.get("type")
    if kind == "literal":
        return bound_spec_cls(kind="literal", value=value.get("value"))
    if kind == "store":
        return bound_spec_cls(
            kind="store",
            path=str(value.get("path") or "/"),
            scope=str(value.get("scope") or "auto"),
            default=value.get("default"),
        )
    if kind == "data":
        return bound_spec_cls(
            kind="data",
            path=str(value.get("path") or "/"),
            default=value.get("default"),
        )
    if kind == "action":
        return bound_spec_cls(
            kind="action",
            name=str(value.get("name") or ""),
            args=value.get("args", {}) if isinstance(value.get("args", {}), dict) else {},
            default=value.get("default"),
            cache_scope=str(value.get("cache_scope") or value.get("scope") or "page"),
        )
    # Keep implicit data-model bindings limited to binding-shaped dicts.
    # Structural payloads such as Breadcrumb segments also carry "path" for
    # navigation and must not be collapsed into a data binding.
    if allow_implicit_path and "path" in value and set(value.keys()) <= {"path", "default"}:
        return bound_spec_cls(
            kind="data",
            path=str(value.get("path") or "/"),
            default=value.get("default"),
        )
    return None


def collect_specs(controller: Any, data: Any) -> list[Any]:
    specs: list[Any] = []
    spec = controller.normalize_spec(data)
    if spec is not None:
        specs.append(spec)
        return specs
    if isinstance(data, dict):
        for value in data.values():
            specs.extend(controller._collect_specs(value))
    elif isinstance(data, list):
        for value in data:
            specs.extend(controller._collect_specs(value))
    return specs


def collect_watch_paths(
    controller: Any,
    data: Any,
    *,
    surface_id: str,
    comp_id: str,
    item: dict[str, Any] | None = None,
) -> set[str]:
    paths: set[str] = set()
    spec = controller.normalize_spec(data)
    if spec is not None:
        if spec.kind == "store" and spec.path:
            paths.add(spec.path)
        elif spec.kind == "action":
            paths.add(controller._with_action_cache(spec, surface_id, comp_id, item).cache_path or "/")
        return paths

    if isinstance(data, str):
        bound_key = controller._extract_inline_store_key(data, item)
        if bound_key:
            paths.add(bound_key)
        return paths

    if isinstance(data, dict):
        for value in data.values():
            paths.update(
                controller._collect_watch_paths(
                    value,
                    surface_id=surface_id,
                    comp_id=comp_id,
                    item=item,
                )
            )
    elif isinstance(data, list):
        for value in data:
            paths.update(
                controller._collect_watch_paths(
                    value,
                    surface_id=surface_id,
                    comp_id=comp_id,
                    item=item,
                )
            )
    return paths


def collect_data_paths(controller: Any, data: Any) -> set[str]:
    paths: set[str] = set()
    spec = controller.normalize_spec(data)
    if spec is not None:
        if spec.kind == "data" and spec.path:
            paths.add(spec.path)
        return paths

    if isinstance(data, str):
        trimmed = data.strip()
        if trimmed.startswith("@data/"):
            paths.add(trimmed[6:])
        return paths

    if isinstance(data, dict):
        for value in data.values():
            paths.update(controller._collect_data_paths(value))
    elif isinstance(data, list):
        for value in data:
            paths.update(controller._collect_data_paths(value))
    return paths


def extract_component_props(comp_def: dict[str, Any]) -> dict[str, Any]:
    component = comp_def.get("component")
    if not isinstance(component, dict) or not component:
        return {}
    c_type = next(iter(component.keys()))
    props = component.get(c_type)
    return props if isinstance(props, dict) else {}


def collect_component_fallback_paths(
    controller: Any,
    comp_def: dict[str, Any],
    *,
    surface_id: str,
    comp_id: str,
    item: dict[str, Any] | None,
    handled_props: set[str],
    renderer: Any,
) -> set[str]:
    fallback: set[str] = set()
    props = controller._extract_component_props(comp_def)
    policies = renderer.binding_strategies() if renderer is not None else {}

    def _collect_direct_children_paths(children_value: Any) -> set[str]:
        paths: set[str] = set()

        spec = controller.normalize_spec(children_value)
        if spec is not None:
            return controller._collect_watch_paths(
                children_value,
                surface_id=surface_id,
                comp_id=comp_id,
                item=item,
            )

        if not isinstance(children_value, dict):
            return paths

        explicit = children_value.get("explicitList")
        spec = controller.normalize_spec(explicit)
        if spec is not None:
            return controller._collect_watch_paths(
                explicit,
                surface_id=surface_id,
                comp_id=comp_id,
                item=item,
            )

        if not isinstance(explicit, list):
            return paths

        for child in explicit:
            if isinstance(child, dict) and "component" in child:
                continue
            child_paths = controller._collect_watch_paths(
                child,
                surface_id=surface_id,
                comp_id=comp_id,
                item=item,
            )
            paths.update(child_paths)
        return paths

    for prop_name, prop_value in props.items():
        if prop_name in {"show_if", "hide_if", "required_permissions", "permissions"}:
            continue
        if prop_name in handled_props:
            continue
        fallback.update(
            controller._collect_watch_paths(
                prop_value,
                surface_id=surface_id,
                comp_id=comp_id,
                item=item,
            )
        )

    for extra_key in ("show_if", "hide_if", "children"):
        if extra_key in {"show_if", "hide_if"}:
            continue
        extra_value = comp_def.get(extra_key)
        if extra_value is None:
            continue
        if extra_key == "children":
            # Legacy behavior walked the whole inline child tree here:
            #
            # extra_paths = controller._collect_watch_paths(
            #     extra_value,
            #     surface_id=surface_id,
            #     comp_id=comp_id,
            #     item=item,
            # )
            #
            # That makes a binding owned by a descendant (for example a Grid
            # style inside a YAML Tabs panel) also register on every ancestor.
            # Store updates then rerender Tabs/Columns unrelated to the target
            # component and can remove/rebuild tab headers. Only direct
            # structural bindings on children belong to the parent; inline
            # child components are bound when their own widgets are built.
            extra_paths = _collect_direct_children_paths(extra_value)
        else:
            extra_paths = controller._collect_watch_paths(
                extra_value,
                surface_id=surface_id,
                comp_id=comp_id,
                item=item,
            )
        if not extra_paths:
            continue
        strategy = policies.get(extra_key)
        if strategy == getattr(renderer, "COMPONENT", "component"):
            controller.window.binder.bind_many(
                sorted(extra_paths),
                lambda cid=comp_id: controller._schedule_component_rerender(cid),
                owner=controller.window._get_widget_by_id(comp_id),
                immediate=False,
            )
            continue
        fallback.update(extra_paths)
    return fallback


def resolve_spec(
    controller: Any,
    spec: Any,
    item: dict[str, Any] | None,
    surface_id: str | None,
) -> Any:
    if spec.kind == "literal":
        return spec.value
    if spec.kind == "store" and spec.path:
        return controller.window.store.get(spec.path, spec.default, spec.scope)
    if spec.kind == "data" and spec.path:
        return controller.read_surface_data(surface_id, spec.path, spec.default)
    if spec.kind == "action":
        if not spec.name:
            return spec.default
        cache_spec = controller._with_action_cache(spec, "main", "anonymous", item)
        return controller.window.store.get(
            cache_spec.cache_path or "/",
            cache_spec.default,
            cache_spec.cache_scope,
        )
    return spec.default


def resolve_string(
    controller: Any,
    data: str,
    item: dict[str, Any] | None,
    surface_id: str | None,
) -> Any:
    trimmed = data.strip()
    if trimmed.startswith("@data/"):
        return controller.read_surface_data(surface_id, trimmed[6:], data)
    if trimmed.startswith("{{") and trimmed.endswith("}}"):
        key = trimmed[2:-2].strip()
        if item and key in item:
            return item[key]
        return controller.window.store.get(key, data, "auto")

    if item is None:
        return data

    resolved = data
    if resolved.startswith("$item."):
        item_key = resolved[6:]
        if item_key in item:
            return item[item_key]

    for key, value in sorted(item.items(), key=lambda entry: len(str(entry[0])), reverse=True):
        resolved = resolved.replace(f"$item.{key}", str(value))
        resolved = resolved.replace(f"{{{{{key}}}}}", str(value))
    return resolved


def extract_inline_store_key(value: str, item: dict[str, Any] | None) -> str | None:
    trimmed = value.strip()
    if not (trimmed.startswith("{{") and trimmed.endswith("}}")):
        return None
    key = trimmed[2:-2].strip()
    if item and key in item:
        return None
    return key if key.startswith("/") else f"/{key}"


def with_action_cache(
    spec: Any,
    item: dict[str, Any] | None,
    *,
    stable_json: Any,
    bound_spec_cls: type,
) -> Any:
    digest_source = {
        "name": spec.name,
        "args": spec.args or {},
        "cache_scope": spec.cache_scope,
        "item": item or {},
    }
    digest = hashlib.sha1(stable_json(digest_source).encode("utf-8")).hexdigest()[:16]
    return bound_spec_cls(
        kind="action",
        name=spec.name,
        args=spec.args,
        default=spec.default,
        cache_scope=spec.cache_scope,
        cache_path=f"/_bindings/actions/{digest}",
    )
