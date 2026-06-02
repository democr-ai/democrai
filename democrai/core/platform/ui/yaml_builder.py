import yaml
from contextlib import nullcontext
from typing import Any, Dict, List, Optional, Union
from democrai.sdk.ui import Builder, ui
from democrai.sdk.components.base import bound, Component
from democrai.core.runtime.observability.profiling import current_request_profiler


def _profile_span(name: str):
    profiler = current_request_profiler()
    if profiler is None:
        return nullcontext()
    return profiler.span(name)

class YamlUIBuilder:
    """
    Constructs A2UI surfaces from YAML definitions.
    
    Example YAML:
        template: full
        components:
          - kind: Card
            title: "My Card"
            children:
              - kind: Text
                text: "Hello from YAML"
                capability: "text.set"
              - kind: Button
                text: "Click Me"
                on_click: "my_module.action"
    """

    def __init__(self, sdk=None):
        self.sdk = sdk

    def build(self, yaml_content: str) -> Builder:
        """
        Parses YAML and builds the corresponding A2UI structure.

        :param yaml_content: The raw YAML string.
        :return: A populated Builder.
        :raises ValueError: If the YAML is invalid or contains unknown components.
        """
        try:
            with _profile_span("yaml.safe_load"):
                data = yaml.safe_load(yaml_content)
        except Exception as e:
            raise ValueError(f"Invalid YAML content: {e}")

        # Ensure we have a builder
        builder = Builder()
        
        # Determine current surface and template if specified at root
        if isinstance(data, dict):
            if "template" in data:
                with _profile_span("yaml.set_template"):
                    builder.set_template(data["template"], session=getattr(self.sdk, "session", None))
            if "surface_id" in data:
                builder.surface_id = data["surface_id"]

        if isinstance(data, list):
            # List of components
            for item in data:
                with _profile_span("yaml.component"):
                    self._add_to_builder_or_list(builder, item, builder)
        elif isinstance(data, dict):
            # Full definition or single component
            if "components" in data and isinstance(data["components"], list):
                for item in data["components"]:
                    with _profile_span("yaml.component"):
                        self._add_to_builder_or_list(builder, item, builder)
            else:
                # Single component at root (excluding root config keys)
                if "kind" in data:
                    with _profile_span("yaml.component"):
                        self._add_to_target(builder, self._parse_component(data, builder))
        
        return builder

    def _add_to_builder_or_list(self, target: Union[Builder, List], item: Any, builder: Optional[Builder] = None):
        """Helper to add component or handle include."""
        if isinstance(item, str) and item.startswith("@include/"):
            included = self._handle_include(item[9:], builder)
            if isinstance(included, list):
                for sub in included:
                    self._add_to_target(target, sub)
            else:
                self._add_to_target(target, included)
        else:
            self._add_to_target(target, self._parse_component(item, builder))

    def _add_to_target(self, target: Union[Builder, List], item: Any):
        if isinstance(target, Builder):
            # Already added inside _parse_component if builder was passed
            if item not in target._components:
                target.add(item)
        else:
            target.append(item)

    def _handle_include(self, filename: str, builder: Optional[Builder] = None) -> Union[Component, List[Component]]:
        """Loads and parses an included YAML file."""
        import os
        base_path = getattr(self.sdk, "module_path", "")
        path = os.path.join(base_path, filename) if base_path else filename
        
        if not os.path.exists(path):
            for ext in [".yaml", ".yml"]:
                if os.path.exists(path + ext):
                    path += ext
                    break
        
        if not os.path.exists(path):
            raise FileNotFoundError(f"Included YAML file not found: {filename}")

        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
            
        data = yaml.safe_load(content)
        if isinstance(data, list):
            return [self._parse_component(item, builder) for item in data]
        elif isinstance(data, dict):
            # If it's a full manifest, we only want the components
            if "components" in data and isinstance(data["components"], list):
                return [self._parse_component(item, builder) for item in data["components"]]
            return self._parse_component(data, builder)
        
        raise ValueError(f"Invalid content in included file: {filename}")

    def _parse_component(self, data: Dict[str, Any], builder: Optional[Builder] = None) -> Component:
        if isinstance(data, str) and data.startswith("@include/"):
            # This shouldn't be called directly for strings, but handle it just in case
            return self._handle_include(data[9:], builder)

        kind = data.get("kind")
        comp_id = data.get("id")
        
        if not comp_id and kind:
            # Generate a stable-ish unique ID for components missing one
            import uuid
            comp_id = f"yaml_{kind.lower()}_{uuid.uuid4().hex[:8]}"
        
        if not kind:
            raise ValueError("Component definition must include a 'kind' property.")
        
        # Use sdk.ui if available (for wrapped/proxied components), otherwise global ui
        ui_source = getattr(self.sdk, "ui", ui)
        comp_cls = getattr(ui_source, kind, None)
        
        if not comp_cls:
            # Last resort: try checking the global ui directly if sdk.ui failed
            comp_cls = getattr(ui, kind, None)
            
        if not comp_cls:
            raise ValueError(f"Unknown UI component kind: '{kind}'.")

        # Extract special properties
        exclude = {"kind", "id", "children", "components", "permissions", "show_if", "hide_if"}
        if kind != "SurfaceHost":
            exclude.add("surface_id")
        with _profile_span("yaml.resolve_props"):
            all_props = {k: self._resolve_value(v) for k, v in data.items() if k not in exclude}
        with _profile_span("yaml.coerce_slots"):
            self._coerce_component_slot_props(all_props)
        
        # Smart instantiation: separate constructor args from extra props
        import inspect
        
        # Unwrap the component if it's wrapped (e.g. by sdk.ui)
        original_comp = inspect.unwrap(comp_cls)
        
        try:
            # If it's a class, check __init__; if it's a function (wrapper), check it directly
            target_for_sig = original_comp.__init__ if inspect.isclass(original_comp) else original_comp
            with _profile_span("yaml.inspect_signature"):
                sig = inspect.signature(target_for_sig)
            constructor_params = sig.parameters
        except (ValueError, TypeError, AttributeError):
            constructor_params = {}

        constructor_args = {"id": comp_id}
        extra_props = {}

        params_str = str(constructor_params).lower()
        has_kwargs = "kwargs" in params_str

        for k, v in all_props.items():
            # If it's a known parameter or the class accepts **kwargs, pass it to constructor
            if k in constructor_params or has_kwargs:
                constructor_args[k] = v
            else:
                extra_props[k] = v

        # Instantiate with as many valid args as possible
        try:
            with _profile_span("yaml.instantiate"):
                component = comp_cls(**constructor_args)
        except TypeError as e:
            # Emergency fallback: if it fails with unexpected keyword, move that keyword to extra_props
            import re
            match = re.search(r"unexpected keyword argument '([^']+)'", str(e))
            if match:
                wrong_key = match.group(1)
                if wrong_key in constructor_args:
                    extra_props[wrong_key] = constructor_args.pop(wrong_key)
                    # Retry once
                    with _profile_span("yaml.instantiate"):
                        component = comp_cls(**constructor_args)
                else:
                    raise
            elif "missing" in str(e) and "text" in constructor_params and "text" not in constructor_args:
                constructor_args["text"] = all_props.get("text", "")
                with _profile_span("yaml.instantiate"):
                    component = comp_cls(**constructor_args)
            else:
                raise TypeError(f"Failed to instantiate {kind}: {e}. Args: {constructor_args}")

        # Set any remaining extra properties
        for k, v in extra_props.items():
            with _profile_span("yaml.set_extra_prop"):
                component.set_prop(k, v)

        # Apply permissions and visibility rules
        if "permissions" in data:
            perms = data["permissions"]
            if isinstance(perms, (list, tuple)):
                component.set_required_permissions(perms)
        
        if "show_if" in data:
            component.set_show_if(self._resolve_value(data["show_if"]))
            
        if "hide_if" in data:
            component.set_hide_if(self._resolve_value(data["hide_if"]))

        if builder:
            builder.add(component)

        # Handle children
        children = data.get("children", [])
        if isinstance(children, list):
            for child_data in children:
                if isinstance(child_data, dict):
                    with _profile_span("yaml.child_component"):
                        component.children.append(self._parse_component(child_data, builder))
                elif isinstance(child_data, str):
                    if child_data.startswith("@include/"):
                        with _profile_span("yaml.include"):
                            included = self._handle_include(child_data[9:], builder)
                        if isinstance(included, list):
                            component.children.extend(included)
                        else:
                            component.children.append(included)
                    else:
                        component.children.append(child_data)
        
        return component

    def _coerce_component_slot_props(self, props: Dict[str, Any]) -> None:
        """
        Ensures that special props that can contain nested component specs
        are correctly converted to Component instances.
        """
        # Multi-component slots
        for key in ("left", "center", "right"):
            raw_value = props.get(key)
            if not isinstance(raw_value, list):
                continue
            normalized: List[Any] = []
            for item in raw_value:
                if isinstance(item, dict) and item.get("kind"):
                    normalized.append(self._parse_component(item))
                    continue
                if isinstance(item, str) and item.startswith("@include/"):
                    included = self._handle_include(item[9:])
                    if isinstance(included, list):
                        normalized.extend(included)
                    else:
                        normalized.append(included)
                    continue
                normalized.append(item)
            props[key] = normalized

        # Single-component slots (like item_template for List/Carousel)
        for key in ("item_template", "itemTemplate"):
            raw_value = props.get(key)
            if isinstance(raw_value, dict) and raw_value.get("kind"):
                props[key] = self._parse_component(raw_value)
            elif isinstance(raw_value, str) and raw_value.startswith("@include/"):
                included = self._handle_include(raw_value[9:])
                # For single slots, we expect exactly one component
                if isinstance(included, list):
                    if len(included) > 0:
                        props[key] = included[0]
                else:
                    props[key] = included

    def _resolve_value(self, value: Any) -> Any:
        """
        Resolves bindings:
        - @state/page/path   -> Local page scope
        - @state/global/path -> Global session scope
        - @state/path        -> Auto scope
        - @data/path         -> Surface data model
        - @t/key             -> Translation (resolved server-side via sdk.i18n.t)
        - @action/name       -> Client action
        - @literal/value     -> Explicit literal
        """
        if isinstance(value, str):
            if value.startswith("@state/"):
                path = value[7:]
                if path.startswith("page/"):
                    return bound.store(path[5:], scope="page")
                if path.startswith("global/"):
                    return bound.store(path[7:], scope="global")
                return bound.store(path, scope="auto")

            if value.startswith("@data/"):
                return bound.data(value[6:])
                
            if value.startswith("@action/"):
                return bound.action(value[8:])
            
            if value.startswith("@tag/"):
                tag_name = value[5:]
                from democrai.core.platform.ui import tags as tag_module
                return getattr(tag_module, tag_name, tag_name)

            if value.startswith("@t/"):
                key = value[3:]
                translator = None
                i18n = getattr(self.sdk, "i18n", None)
                if i18n is not None:
                    translator = getattr(i18n, "t", None)
                if callable(translator):
                    try:
                        return translator(key)
                    except Exception:
                        return key
                return key
            
            if value.startswith("@literal/"):
                return bound.literal(value[9:])
        
        if isinstance(value, list):
            return [self._resolve_value(v) for v in value]
        if isinstance(value, dict):
            return {k: self._resolve_value(v) for k, v in value.items()}
            
        return value

def ui_from_yaml(yaml_content: str, sdk=None) -> Builder:
    """
    Helper function to create an Builder from a YAML definition.

    :param yaml_content: The YAML UI definition.
    :param sdk: Optional ModuleSDK instance for context.
    :return: An Builder instance.
    """
    return YamlUIBuilder(sdk).build(yaml_content)
