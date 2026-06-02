from clients.qtdesktop.ui.renderers.base import BaseRenderer


class _Bindings:
    def __init__(self, store):
        self.store = store

    def resolve_value(self, value, item=None):
        if isinstance(value, dict) and "path" in value:
            return self.store.get(value["path"])
        if isinstance(value, str) and value.startswith("{{") and value.endswith("}}"):
            key = value[2:-2].strip()
            if item and key in item:
                return item[key]
            return self.store.get(f"/{key}")
        return value


class _Store:
    def __init__(self, data):
        self.data = data

    def get(self, key, default=None):
        return self.data.get(key, default)


class _Renderer(BaseRenderer):
    component_type = "Text"

    def render(self, props, surface_id, app_instance, comp_id="unknown"):
        return None


def _component(props):
    return {"id": "c1", "component": {"Text": props}, "children": {"explicitList": []}}


def _app(*, permissions=None, role="User", store=None):
    store = store or _Store({})
    return type(
        "App",
        (),
        {
            "user_permissions": permissions or [],
            "user_role": role,
            "bindings": _Bindings(store),
        },
    )()


def test_component_visibility_defaults_to_visible():
    renderer = _Renderer()

    assert renderer.is_component_visible(_component({}), _app()) is True


def test_component_visibility_applies_required_permissions():
    renderer = _Renderer()
    component = _component({"required_permissions": ["admin.view"]})

    assert renderer.is_component_visible(component, _app()) is False
    assert renderer.is_component_visible(component, _app(permissions=["admin.view"])) is True


def test_component_visibility_uses_any_matching_required_permission_and_super_bypass():
    renderer = _Renderer()
    component = _component({"required_permissions": ["admin.view", "audit.read"]})

    assert renderer.is_component_visible(component, _app(permissions=["audit.read"])) is True
    assert renderer.is_component_visible(component, _app(permissions=["other.permission"])) is False
    assert renderer.is_component_visible(component, _app(role="super")) is True


def test_component_visibility_applies_show_if_and_hide_if():
    renderer = _Renderer()
    component = _component(
        {
            "show_if": {
                "mode": "AND",
                "conditions": [{"left": {"type": "store", "path": "/flag"}, "op": "==", "right": True}],
            },
            "hide_if": {
                "mode": "OR",
                "conditions": [{"left": "{{kind}}", "op": "==", "right": "hidden"}],
            },
        }
    )

    assert renderer.is_component_visible(
        component,
        _app(store=_Store({"/flag": False})),
        {"kind": "visible"},
    ) is False
    assert renderer.is_component_visible(
        component,
        _app(store=_Store({"/flag": True})),
        {"kind": "visible"},
    ) is True
    assert renderer.is_component_visible(
        component,
        _app(store=_Store({"/flag": True})),
        {"kind": "hidden"},
    ) is False


def test_component_visibility_applies_multiple_and_conditions():
    renderer = _Renderer()
    component = _component(
        {
            "required_permissions": ["reports.view", "reports.audit"],
            "show_if": {
                "mode": "AND",
                "conditions": [
                    {"left": {"type": "store", "path": "/flag"}, "op": "==", "right": True},
                    {"left": "{{count}}", "op": ">=", "right": 3},
                ],
            },
        }
    )

    assert renderer.is_component_visible(
        component,
        _app(permissions=["reports.view"], store=_Store({"/flag": True})),
        {"count": 3},
    ) is True
    assert renderer.is_component_visible(
        component,
        _app(permissions=["reports.view"], store=_Store({"/flag": False})),
        {"count": 3},
    ) is False
    assert renderer.is_component_visible(
        component,
        _app(permissions=["reports.view"], store=_Store({"/flag": True})),
        {"count": 2},
    ) is False


def test_component_visibility_applies_multiple_or_conditions():
    renderer = _Renderer()
    component = _component(
        {
            "show_if": {
                "mode": "OR",
                "conditions": [
                    {"left": {"type": "store", "path": "/tier"}, "op": "==", "right": "gold"},
                    {"left": "{{kind}}", "op": "==", "right": "priority"},
                ],
            }
        }
    )

    assert renderer.is_component_visible(
        component,
        _app(store=_Store({"/tier": "gold"})),
        {"kind": "standard"},
    ) is True
    assert renderer.is_component_visible(
        component,
        _app(store=_Store({"/tier": "silver"})),
        {"kind": "priority"},
    ) is True
    assert renderer.is_component_visible(
        component,
        _app(store=_Store({"/tier": "silver"})),
        {"kind": "standard"},
    ) is False


def test_component_visibility_hides_when_any_or_hide_condition_matches():
    renderer = _Renderer()
    component = _component(
        {
            "required_permissions": ["admin.view"],
            "hide_if": {
                "mode": "OR",
                "conditions": [
                    {"left": {"type": "store", "path": "/suspended"}, "op": "==", "right": True},
                    {"left": "{{status}}", "op": "==", "right": "archived"},
                ],
            },
        }
    )

    assert renderer.is_component_visible(
        component,
        _app(permissions=["admin.view"], store=_Store({"/suspended": False})),
        {"status": "active"},
    ) is True
    assert renderer.is_component_visible(
        component,
        _app(permissions=["admin.view"], store=_Store({"/suspended": True})),
        {"status": "active"},
    ) is False
    assert renderer.is_component_visible(
        component,
        _app(permissions=["admin.view"], store=_Store({"/suspended": False})),
        {"status": "archived"},
    ) is False


def test_component_visibility_hides_only_when_all_and_hide_conditions_match():
    renderer = _Renderer()
    component = _component(
        {
            "hide_if": {
                "mode": "AND",
                "conditions": [
                    {"left": {"type": "store", "path": "/maintenance"}, "op": "==", "right": True},
                    {"left": "{{role}}", "op": "==", "right": "readonly"},
                ],
            }
        }
    )

    assert renderer.is_component_visible(
        component,
        _app(store=_Store({"/maintenance": True})),
        {"role": "editor"},
    ) is True
    assert renderer.is_component_visible(
        component,
        _app(store=_Store({"/maintenance": False})),
        {"role": "readonly"},
    ) is True
    assert renderer.is_component_visible(
        component,
        _app(store=_Store({"/maintenance": True})),
        {"role": "readonly"},
    ) is False


def test_component_visibility_supports_contains_and_in_operators():
    renderer = _Renderer()
    contains_component = _component(
        {
            "show_if": {
                "mode": "AND",
                "conditions": [
                    {"left": {"type": "store", "path": "/tags"}, "op": "contains", "right": "security"},
                    {"left": "{{state}}", "op": "in", "right": ["draft", "review"]},
                ],
            }
        }
    )

    assert renderer.is_component_visible(
        contains_component,
        _app(store=_Store({"/tags": ["security", "ops"]})),
        {"state": "review"},
    ) is True
    assert renderer.is_component_visible(
        contains_component,
        _app(store=_Store({"/tags": ["ops"]})),
        {"state": "review"},
    ) is False
    assert renderer.is_component_visible(
        contains_component,
        _app(store=_Store({"/tags": ["security", "ops"]})),
        {"state": "published"},
    ) is False


def test_component_visibility_fails_closed_for_invalid_or_unknown_conditions():
    renderer = _Renderer()
    component = _component(
        {
            "show_if": {
                "mode": "AND",
                "conditions": [
                    {"left": {"type": "store", "path": "/count"}, "op": ">", "right": "not-a-number"},
                    {"left": "{{status}}", "op": "matches", "right": "active"},
                ],
            },
            "hide_if": {
                "mode": "OR",
                "conditions": [
                        {"left": {"type": "store", "path": "/items"}, "op": "contains", "right": "x"},
                ],
            },
        }
    )

    assert renderer.is_component_visible(
        component,
        _app(store=_Store({"/count": 3, "/items": None})),
        {"status": "active"},
    ) is False


def test_component_visibility_empty_condition_sets_are_not_treated_as_matches():
    renderer = _Renderer()
    component = _component(
        {
            "show_if": {"mode": "AND", "conditions": []},
            "hide_if": {"mode": "OR", "conditions": []},
        }
    )

    assert renderer.is_component_visible(component, _app()) is False


def test_component_visibility_fails_closed_when_required_binding_values_are_missing():
    renderer = _Renderer()
    component = _component(
        {
            "show_if": {
                "mode": "AND",
                "conditions": [
                        {"left": {"type": "store", "path": "/missing-flag"}, "op": "==", "right": True},
                    {"left": "{{missing_item}}", "op": "==", "right": "ok"},
                ],
            }
        }
    )

    assert renderer.is_component_visible(
        component,
        _app(store=_Store({})),
        {"kind": "visible"},
    ) is False


def test_component_visibility_treats_null_bound_values_as_non_matching():
    renderer = _Renderer()
    component = _component(
        {
            "show_if": {
                "mode": "OR",
                "conditions": [
                        {"left": {"type": "store", "path": "/tier"}, "op": "==", "right": "gold"},
                    {"left": "{{score}}", "op": ">=", "right": 10},
                ],
            }
        }
    )

    assert renderer.is_component_visible(
        component,
        _app(store=_Store({"/tier": None})),
        {"score": None},
    ) is False
