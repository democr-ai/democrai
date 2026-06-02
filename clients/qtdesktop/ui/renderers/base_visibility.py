from __future__ import annotations

from typing import Any


def get_component_props(component_data: dict[str, Any]) -> dict[str, Any]:
    component = component_data.get("component")
    if not isinstance(component, dict) or not component:
        return {}
    c_type = next(iter(component.keys()))
    props = component.get(c_type)
    return props if isinstance(props, dict) else {}


def is_super_role(role: Any) -> bool:
    normalized = str(role or "").strip().lower()
    return normalized in {"super", "admin"}


def has_required_permissions(required: Any, permissions: Any) -> bool:
    if isinstance(required, str):
        required_values = [required.strip()] if required.strip() else []
    elif isinstance(required, (list, tuple)):
        required_values = [str(item).strip() for item in required if str(item).strip()]
    else:
        required_values = []
    if not required_values:
        return True
    permission_values = (
        [str(item).strip() for item in permissions if str(item).strip()]
        if isinstance(permissions, list)
        else []
    )
    return any(value in permission_values for value in required_values)


def permissions_allow(component_data: dict[str, Any], app_instance: Any) -> bool:
    props = get_component_props(component_data)
    required = props.get(
        "required_permissions", component_data.get("required_permissions")
    )
    if required is None:
        required = component_data.get("permissions", [])
    if isinstance(required, str):
        required = [required]
    if not required:
        return True

    store = getattr(app_instance, "store", None)
    role = getattr(app_instance, "user_role", "Guest")
    if store is not None:
        role = store.get("/auth/role", role, "global")
    if is_super_role(role):
        return True
    permissions = getattr(app_instance, "user_permissions", [])
    if store is not None:
        permissions = store.get("/auth/permissions", permissions, "global")
    return has_required_permissions(required, permissions)


def resolve_required_permissions(spec: dict[str, Any]) -> list[str]:
    required = spec.get("required_permissions") or []
    if isinstance(required, str):
        return [required]
    if isinstance(required, (list, tuple)):
        return [str(item).strip() for item in required if str(item).strip()]
    return []


def permissions_allow_for_spec(spec: dict[str, Any], app_instance: Any) -> bool:
    required = resolve_required_permissions(spec)
    if not required:
        return True

    store = getattr(app_instance, "store", None)
    role = getattr(app_instance, "user_role", "Guest")
    if store is not None:
        role = store.get("/auth/role", role, "global")
    if is_super_role(role):
        return True

    permissions = getattr(app_instance, "user_permissions", [])
    if store is not None:
        permissions = store.get("/auth/permissions", permissions, "global")
    return has_required_permissions(required, permissions)


def resolve_condition_value(
    value: Any,
    app_instance: Any,
    item: dict[str, Any] | None,
    surface_id: str | None = None,
) -> Any:
    bindings = getattr(app_instance, "bindings", None)
    if bindings is not None:
        if hasattr(bindings, "resolve_value_for_surface"):
            return bindings.resolve_value_for_surface(value, surface_id, item)
        if hasattr(bindings, "resolve_value"):
            return bindings.resolve_value(value, item)
    return value


def evaluate_condition(
    condition: dict[str, Any],
    app_instance: Any,
    item: dict[str, Any] | None,
    surface_id: str | None = None,
) -> bool:
    left = resolve_condition_value(
        condition.get("left", condition.get("value1")), app_instance, item, surface_id
    )
    right = resolve_condition_value(
        condition.get("right", condition.get("value2")), app_instance, item, surface_id
    )
    comparator = condition.get("op", condition.get("operator"))

    try:
        if comparator == "==":
            return left == right
        if comparator == "!=":
            return left != right
        if comparator == ">":
            return float(left) > float(right)
        if comparator == "<":
            return float(left) < float(right)
        if comparator == ">=":
            return float(left) >= float(right)
        if comparator == "<=":
            return float(left) <= float(right)
        if comparator == "in":
            return left in right
        if comparator == "contains":
            return right in left
    except Exception:
        return False
    return False


def evaluate_visibility_rule(
    rule: Any,
    app_instance: Any,
    item: dict[str, Any] | None,
    surface_id: str | None = None,
    *,
    default: bool,
) -> bool:
    if rule is None:
        return default
    if isinstance(rule, bool):
        return rule
    if not isinstance(rule, dict):
        return bool(rule)

    mode = str(rule.get("mode") or rule.get("operator") or "AND").upper()
    conditions = rule.get("conditions", [])
    if not isinstance(conditions, list) or not conditions:
        conditions = [rule]

    results = [
        evaluate_condition(condition, app_instance, item, surface_id)
        for condition in conditions
        if isinstance(condition, dict)
    ]
    if not results:
        return default
    if mode == "OR":
        return any(results)
    return all(results)


def spec_is_visible(
    spec: dict[str, Any],
    app_instance: Any,
    item: dict[str, Any] | None,
    surface_id: str | None = None,
) -> bool:
    def _eval_spec_rule(rule: Any, *, default: bool) -> bool:
        if rule is None:
            return default
        if isinstance(rule, dict):
            if "conditions" in rule or "operator" in rule or "mode" in rule:
                return evaluate_visibility_rule(
                    rule,
                    app_instance,
                    item,
                    surface_id,
                    default=default,
                )
            if (
                "left" in rule
                or "right" in rule
                or "value1" in rule
                or "value2" in rule
                or "op" in rule
            ):
                return evaluate_condition(rule, app_instance, item, surface_id)
            return bool(rule)
        return bool(rule)

    show_if = spec.get("show_if")
    if show_if is not None and not _eval_spec_rule(show_if, default=True):
        return False

    hide_if = spec.get("hide_if")
    if hide_if is not None and _eval_spec_rule(hide_if, default=False):
        return False

    return permissions_allow_for_spec(spec, app_instance)
