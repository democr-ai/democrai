from typing import Dict, Any, Optional, List, Union, Iterable


class _BoundFactory:
    """Factory that produces bound-value payloads for the A2UI contract."""

    def __call__(self, path: str, **kwargs) -> dict:
        """Shortcut for :meth:`store`."""
        return self.store(path, **kwargs)

    def literal(self, value: Any) -> dict:
        """Create a literal-value payload."""
        return {"type": "literal", "value": value}

    def store(
        self,
        path: str,
        *,
        scope: str = "auto",
        default: Any = None,
    ) -> dict:
        """Create a store-bound value payload."""
        return {"type": "store", "path": path, "scope": scope, "default": default}

    def data(
        self,
        path: str,
        *,
        default: Any = None,
    ) -> dict:
        """Create a surface data-model bound value payload."""
        return {"path": path, "default": default}

    def action(
        self,
        name: str,
        *,
        args: Optional[dict[str, Any]] = None,
        default: Any = None,
        cache_scope: str = "page",
    ) -> dict:
        """Create an action-bound value payload."""
        return {
            "type": "action",
            "name": name,
            "args": args if args is not None else {},
            "default": default,
            "cache_scope": cache_scope,
        }


bound = _BoundFactory()


def LiteralValue(value: Any) -> dict:
    """Explicit literal value in the bound-value contract."""
    return bound.literal(value)


def ActionBoundValue(
    name: str,
    *,
    args: Optional[dict[str, Any]] = None,
    default: Any = None,
    cache_scope: str = "page",
) -> dict:
    """Resolve a client-bound value by invoking an action."""
    return bound.action(name, args=args, default=default, cache_scope=cache_scope)


class Component:
    """
    Base class for all A2UI components.

    A component represents a UI element that can be serialized and sent to
    the client. It supports properties, children, and reactive bindings.
    """

    type: str = "Component"

    def __init__(self, id: str, permissions: Optional[list] = None):
        self.id = id
        self.props: Dict[str, Any] = {}
        self.permissions = permissions if permissions is not None else []
        self.children: List[Union[str, "Component"]] = []
        self._allowed_capabilities: set[str] = set()
        self._denied_capabilities: set[str] = set()
        self._capabilities_explicit = False

    def _serialize_value(self, value: Any) -> Any:
        """Recursively serialize nested SDK values into protocol-safe payloads."""
        if isinstance(value, Component):
            return value.to_dict()
        if isinstance(value, dict):
            return {key: self._serialize_value(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._serialize_value(item) for item in value]
        if isinstance(value, tuple):
            return [self._serialize_value(item) for item in value]
        to_dict = getattr(value, "to_dict", None)
        if callable(to_dict):
            return self._serialize_value(to_dict())
        return value

    def to_dict(self) -> Dict[str, Any]:
        """
        Serializes the component and its children to a protocol-compliant dictionary.

        :return: A dictionary representing the component's state and structure.
        """
        props = {key: self._serialize_value(value) for key, value in self.props.items()}
        if self.permissions and "required_permissions" not in props:
            props["required_permissions"] = list(self.permissions)

        declared_capabilities = props.get("capabilities")
        capabilities = self.get_capabilities()
        merged_capabilities = self._normalize_capabilities(capabilities)
        if isinstance(declared_capabilities, (list, tuple, set)):
            merged_capabilities.update(self._normalize_capabilities(declared_capabilities))
        if merged_capabilities:
            props["capabilities"] = sorted(merged_capabilities)

        # If children are Component objects, convert them to dicts (recursive)
        # Otherwise keep them as IDs (flat)
        resolved_children: List[Union[str, Dict[str, Any]]] = []
        for child in self.children:
            if isinstance(child, Component):
                resolved_children.append(child.to_dict())
            else:
                resolved_children.append(child)

        data = {
            "id": self.id,
            "component": {self.type: props},
            "children": {"explicitList": resolved_children},
        }
        if self.permissions:
            data["permissions"] = self.permissions
        return data

    def set_prop(self, key: str, value: Any):
        """Set a component property and return ``self`` for chaining."""
        self.props[key] = value
        return self

    def set_property(self, key: str, value: Any):
        """Alias for set_prop to match common naming."""
        return self.set_prop(key, value)

    def set_action(self, name: str, context: Optional[dict[str, Any]] = None):
        """Attach a primary action specification to the component."""
        self.set_prop("action", {"name": name, "context": context if context is not None else {}})
        return self

    def set_on_change_action(
        self,
        name: str,
        context: Optional[dict[str, Any]] = None,
        *,
        mode: str = "local",
    ):
        """Attach an on-change action and its dispatch mode."""
        self.set_prop("onChangeAction", {"name": name, "context": context if context is not None else {}})
        self.set_prop("onChangeMode", mode)
        return self

    def collect_input_ids(self, *input_ids: str):
        """Declare input ids whose values should be collected on action dispatch."""
        self.set_prop(
            "collect_input_ids",
            [str(input_id) for input_id in input_ids if str(input_id).strip()],
        )
        return self

    def track_loading(self, *action_names: str):
        """Bind one or more action names to the component loading state."""
        names = [str(action_name) for action_name in action_names if str(action_name).strip()]
        if not names:
            return self
        self.set_prop("track_loading", names[0] if len(names) == 1 else names)
        return self

    def set_error(self, message: str):
        """Sets an error message to be displayed for the component."""
        self.set_prop("error", message)
        return self

    def set_required_permissions(self, permissions: list[str] | tuple[str, ...]):
        """Declare permissions required for the component to be visible or usable."""
        self.props["required_permissions"] = list(permissions)
        return self

    def set_show_if(self, rule: dict[str, Any]):
        """Attach a positive visibility rule."""
        self.props["show_if"] = rule
        return self

    def set_hide_if(self, rule: dict[str, Any]):
        """Attach a negative visibility rule."""
        self.props["hide_if"] = rule
        return self

    def set_animation(self, animation: Any):
        """Attach a declarative animation specification."""
        self.props["animation"] = animation
        return self

    def set_auto_refresh(self, seconds: int, on_refresh: Optional[Union[str, dict]] = None):
        """
        Enables automatic client-side refresh for this component.

        :param seconds: Interval in seconds between refreshes.
        :param on_refresh: The action to trigger on each tick.
                           If None, the renderer may use a default (like on_page_change for DataTable).
        """
        if seconds and seconds > 0:
            self.set_prop("auto_refresh", seconds)
            if on_refresh:
                if isinstance(on_refresh, str):
                    self.set_prop("on_refresh", {"name": on_refresh, "context": {}})
                else:
                    self.set_prop("on_refresh", on_refresh)
        return self

    @staticmethod
    def capability_key(property_name: str, action: str = "set") -> str:
        """Return the canonical ``property.action`` capability identifier."""
        prop_key = str(property_name or "*").strip() or "*"
        action_key = str(action or "set").strip() or "set"
        return f"{prop_key}.{action_key}"

    def set_capabilities(self, capabilities: Iterable[str]):
        """Replace the explicit capability set for this component."""
        self._capabilities_explicit = True
        self._allowed_capabilities = self._normalize_capabilities(capabilities)
        self._denied_capabilities.clear()
        return self

    def allow(self, *capabilities: str):
        """Add capabilities that the client may use for incremental updates."""
        self._capabilities_explicit = True
        self._allowed_capabilities.update(self._normalize_capabilities(capabilities))
        return self

    def deny(self, *capabilities: str):
        """Deny capabilities even when they would otherwise be allowed."""
        self._capabilities_explicit = True
        self._denied_capabilities.update(self._normalize_capabilities(capabilities))
        return self

    def get_capabilities(self) -> list[str]:
        """Return the effective capabilities exposed by the component."""
        if self._capabilities_explicit:
            merged = self._allowed_capabilities - self._denied_capabilities
        else:
            merged = self._default_capabilities()
        return sorted(merged)

    def is_capability_allowed(self, property_name: str, action: str = "set") -> bool:
        """Return whether a property/action mutation is currently authorized."""
        allowed = set(self.get_capabilities())
        if not allowed:
            return False
        prop_key = str(property_name or "").strip()
        action_key = str(action or "set").strip() or "set"
        if not prop_key:
            return False
        candidates = {
            self.capability_key(prop_key, action_key),
            self.capability_key(prop_key, "*"),
            self.capability_key("*", action_key),
            self.capability_key("*", "*"),
        }
        return any(candidate in allowed for candidate in candidates)

    def readonly(self):
        """Make the component expose no mutable capabilities."""
        return self.set_capabilities(())

    def _mutable_property(self, property_name: str):
        """Expose a scalar property as mutable for ``set`` and ``append`` updates."""
        return self.allow(
            self.capability_key(property_name, "set"),
            self.capability_key(property_name, "append"),
        )

    def mutable_text(self, property_name: str = "text"):
        """Convenience helper for a mutable text property."""
        return self._mutable_property(property_name)

    def mutable_value(self, property_name: str = "value"):
        """Convenience helper for a mutable scalar value property."""
        return self._mutable_property(property_name)

    def mutable_collection(self, property_name: str):
        """Expose a collection property for set/append/remove/replace updates."""
        return self.allow(
            self.capability_key(property_name, "set"),
            self.capability_key(property_name, "append"),
            self.capability_key(property_name, "remove"),
            self.capability_key(property_name, "replace"),
        )

    def interactive(self):
        """Mark the component as interactive in the capability contract."""
        return self.allow("visible.set", "enabled.set")

    def _default_capabilities(self) -> set[str]:
        """Return default capabilities for the component type."""
        return set()

    @staticmethod
    def _normalize_capabilities(capabilities: Iterable[str]) -> set[str]:
        """Normalize nested capability iterables into a flat capability set."""
        normalized: set[str] = set()
        for cap in capabilities:
            if cap is None:
                continue
            if isinstance(cap, (list, tuple, set)):
                normalized.update(Component._normalize_capabilities(cap))
                continue
            cap_key = str(cap).strip()
            if cap_key:
                normalized.add(cap_key)
        return normalized
