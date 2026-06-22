# YAML, Resources, and Routing Helpers

This section covers the rest of the `ui` facade:

- `resolve_route(...)`
- `resolve_resource(...)`
- `resolve_media_source(...)`
- `from_yaml(...)`
- `load(...)`
- `prepare_shell_surface(...)`
- `mount_shell_frame(...)`
- `nav_active_path_rule(...)`

The module-level `Router` helper is also covered here because it is routing
plumbing rather than a component API.

These helpers matter because they keep UI authoring aligned with the runtime’s actual routing, resource resolution, and shell composition behavior.

## `resolve_route(route, session, extra_params=None)`

This method resolves a route through the main application router.

Example:

```python
resolved = module_sdk.ui.resolve_route(
    "/system/user/7/view",
    session,
)
```

### Important Detail

This is a synchronous helper. It delegates directly to the main application router’s `resolve(...)` and returns the resolved payload immediately.

Use it when you need to inspect how the router would resolve a path instead of simply navigating to it.

This is not a normal rendering entrypoint for most modules, but it is useful for advanced routing-aware flows.

## `resolve_resource(resource) -> str`

This method resolves a module-relative static resource path.

Example:

```python
icon_path = module_sdk.ui.resolve_resource("assets/icons/user.svg")
```

Use it when you need the same module-relative resource resolution rules that wrapped UI constructors already apply automatically.

## `resolve_media_source(value, *, component_type, field) -> str`

This method resolves and, when appropriate, proxies a media source for one component field.

Example:

```python
image_url = module_sdk.ui.resolve_media_source(
    "assets/preview.png",
    component_type="Image",
    field="url",
)
```

### What It Is For

Use it when you are composing media-related component payloads manually and want the same safety/path behavior that wrapped components would apply for you.

### What It Actually Does

The method:

1. resolves the path as a module resource
2. creates a small component-type stub
3. runs the same media-field proxy logic used by wrapped constructors

So this is the manual equivalent of “let the wrapped component normalize the media field for me”.

## `from_yaml(yaml_content) -> Builder`

Builds a `Builder` from raw YAML UI content.

Example:

```python
builder = module_sdk.ui.from_yaml(
    \"\"\"
- kind: Column
  id: root
  children:
    - kind: Text
      id: title
      text: Users
\"\"\"
)
```

Use it when your UI structure already exists as a YAML string rather than a file on disk.

## `load(filename) -> Builder`

Loads a YAML file from the current module path and builds its UI.

Example:

```python
builder = module_sdk.ui.load("ui/yaml/user_list")
```

### What It Actually Does

The method:

1. joins the requested path against `self.sdk.module_path`
2. if that exact path does not exist, tries `.yaml` and `.yml`
3. reads the file
4. delegates to `from_yaml(...)`

This is the standard YAML-first authoring path for modules.

### Why It Matters

Most module pages should prefer this over large Python-only builders unless there is a concrete reason not to.

## `prepare_shell_surface(...) -> str`

Prepares a shell-mounted surface by:

- binding the builder to a `surface_id`
- setting the `shell_route`
- creating an empty content column

Example:

```python
content_id = module_sdk.ui.prepare_shell_surface(
    builder,
    surface_id="users_content",
    shell_route="/system/users",
    content_component_id="users_content_root",
)
```

Use it when the page content is going to be mounted into a shell surface and you want a predictable content placeholder.

## `mount_shell_frame(...) -> tuple[str, str]`

Builds a common shell frame with:

- a navigation container
- a content scroll area
- a `SurfaceHost` for the content surface

Example:

```python
root_id, host_id = module_sdk.ui.mount_shell_frame(
    builder,
    nav_component_id="user_nav",
    content_surface_id="users_content",
)
```

### What It Is For

Use it when you want a standard split-shell layout without rebuilding that frame structure by hand each time.

### What It Actually Builds

The helper wires together:

- a root `Row`
- a `Splitter`
- a navigation `Column`
- a content `ScrollArea`
- a `SurfaceHost`

This is a layout convenience, not a special rendering mode.

## `nav_active_path_rule(path) -> dict[str, Any]`

Returns the condition payload used to detect whether a navigation item should be considered active based on `/current_path` in global store.

Example:

```python
rule = module_sdk.ui.nav_active_path_rule("/system/users")
```

### Important Behavior

If the path is exactly `"/<module_name>"`, the helper returns a simple equality rule.

For any other path, it returns an `OR` condition that treats both:

- exact equality
- and `contains "<path>/"` 

as active matches.

This is useful because subsection pages usually still want the parent nav entry highlighted.

## Module-Level `Router`

`democrai.sdk.ui.Router` exposes two static helpers:

- `Router.invalidate_module_routes(module_name)`
- `Router.parse_path(path)`

`invalidate_module_routes(...)` clears cached route entries for one module.
Use it only in infrastructure or module-lifecycle flows where the route table
has changed.

`parse_path(...)` parses a route path through the main application router and
returns the parsed result directly.

Normal page code should use `module_sdk.ui.resolve_route(...)` when it needs to
resolve a route in the context of the current SDK instance.

## Practical Guidance

Use these helpers to stay aligned with the runtime instead of rebuilding path, resource, and shell logic ad hoc.

In particular:

- prefer `load(...)` for YAML-first pages
- use `resolve_media_source(...)` only when you are building media payloads manually
- use `mount_shell_frame(...)` for repeated shell layouts instead of duplicating the same row/splitter/host structure
