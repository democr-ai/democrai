# Builder and Surface Messages

This section covers the most important practical part of the `ui` domain:

- `Builder`
- component wrapping through `module_sdk.ui.<Component>(...)`
- builder state seeding
- surface/data/store message builders

If you understand this page, you understand the part of `sdk.ui` that module authors use every day.

## Wrapped Component Constructors

When you call:

```python
module_sdk.ui.Text("title", "Users")
```

you are not calling the raw component class directly.

The facade wraps public component constructors so it can:

- resolve module-relative resource paths
- proxy supported media fields through the client-safe media resolver
- normalize `action={...}` dictionaries into the constructor shape components expect

That is one reason module code should prefer `module_sdk.ui.Text(...)` over importing raw component classes directly.

## `Builder()`

`Builder` is the programmatic surface builder used to collect components, seed state, and serialize UI protocol payloads.

Example:

```python
builder = module_sdk.ui.Builder()
builder.add(module_sdk.ui.Text("title", "Users"))
builder.set_surface("users_main")
```

### What It Is For

Use `Builder` when:

- the page is written directly in Python
- you loaded a YAML structure and want to enrich or mutate it
- you need to emit low-level SDUI payloads such as `surfaceUpdate`, `dataModelUpdate`, or `stateUpdate`

## `add(component)`

Adds one already-created component to the builder.

Example:

```python
builder.add(module_sdk.ui.Button("refresh_btn", "Refresh", action="users.refresh"))
```

This is the most basic composition method in the builder.

## `get_component(component_id) -> Component | None`

Returns a managed component by id if present.

Example:

```python
title = builder.get_component("title")
if title is not None:
    title.set_prop("text", {"literalString": "Updated title"})
```

Use this as an inspection or advanced composition helper.

For module pages, prefer this direction:

1. define structure, layout, component ids, actions, and bindings in YAML;
2. load the YAML builder from Python;
3. seed data with `set_data(...)` and page/global store values with
   `set_store(...)`;
4. update already mounted components from actions with incremental effects.

Do not use `get_component(...).set_property(...)` as the normal way to populate
a YAML-authored page. If a value can be expressed through a YAML binding, bind it
in YAML and seed the value from Python.

`get_component(...)` is appropriate when you are writing lower-level UI tooling,
building programmatic component fragments, or handling a narrow case that the
documented binding system cannot express.

## `get_roots() -> list[Component]`

Returns the builder-managed components that are not referenced as children of other managed components.

This is mainly useful when you need to inspect or reuse the root-level structure of a builder, especially after loading YAML or merging component groups.

It is less common in normal page code, but it is a real part of the facade and worth knowing about.

## `snapshot(include_components=True, component_serializer=None) -> dict`

Returns a serializable snapshot of the builder transport state.

The snapshot contains data model values, page/global store seed values, template metadata, surface metadata, and component payloads when `include_components` is enabled.

Example:

```python
builder = module_sdk.ui.Builder()
builder.set_surface("users_main", shell_route="/system/users")
builder.set_template("full", session=session)
builder.set_data("/filters/search", "")
builder.set_store("/users/page", 1, scope="page")
builder.add(module_sdk.ui.Text("title", "Users"))

payload = builder.snapshot()
```

### What It Is For

Use `snapshot(...)` when code needs a complete builder payload that can be passed across helper/runtime boundaries without keeping the original builder object.

For state-only handoff, omit components:

```python
payload = builder.snapshot(include_components=False)
```

If the receiver needs a different component representation, pass `component_serializer`:

```python
payload = builder.snapshot(
    component_serializer=lambda component: component.to_dict()
)
```

## `merge(source, components=False, metadata=False, replace=False, component_factory=None)`

Merges transport state from another builder or from a snapshot dictionary.

Example:

```python
page = module_sdk.ui.load("ui/yaml/users_list")

runtime_state = module_sdk.ui.Builder()
runtime_state.set_data("/filters/status", "active")
runtime_state.set_store("/users/loading", False, scope="page")

page.merge(runtime_state)
```

### Default Behavior

By default, `merge(...)` merges only:

- surface data model
- page/global store seed data

Components and metadata are not copied unless requested.

### Copying Components

Use `components=True` when the target builder should also receive the source components:

```python
target = module_sdk.ui.Builder()
target.merge(page, components=True)
```

### Copying Surface Metadata

Use `metadata=True` when the target should inherit template, template dimensions, template components, surface id, and shell route:

```python
target.merge(page, components=True, metadata=True)
```

### Replacing Instead Of Merging

Use `replace=True` when the target builder should be overwritten by the source payload:

```python
target.merge(
    page.snapshot(),
    components=True,
    metadata=True,
    replace=True,
)
```

### Restoring Serialized Components

When `source` is a snapshot dictionary, component entries are dictionaries. Use `component_factory` if the receiver needs each dictionary converted into another object:

```python
class SerializedComponent:
    def __init__(self, payload):
        self._payload = payload

    def to_dict(self):
        return self._payload


target.merge(
    payload,
    components=True,
    replace=True,
    component_factory=lambda item: SerializedComponent(item),
)
```

Most module pages do not need `component_factory`; it is mainly useful for runtime or infrastructure code that restores snapshots.

## `merge_builders(base_builder, extra_builder)`

Merges builder state from `extra_builder` into `base_builder`, then appends only components whose ids are not already present in `base_builder`.

Example:

```python
from democrai.sdk.ui import merge_builders

page = module_sdk.ui.load("ui/yaml/user_detail")

header = module_sdk.ui.Builder()
header.add(module_sdk.ui.Title("user_title", "User detail", level=2))
header.set_store("/user/sidebar_open", True, scope="page")

merge_builders(page, header)
```

### What It Is For

Use this helper when multiple UI helper functions produce builder fragments that must be assembled into one page without duplicating components by id.

Use `Builder.merge(...)` instead when the caller needs explicit control over `components`, `metadata`, or `replace`.

## `set_data(path, value)`

Seeds the surface data model using slash-style paths.

Example:

```python
builder.set_data("/filters/search", "Users")
```

### What It Is For

Use it when a component reads from the surface data model, for example through `@data/...` bindings.

### Important Meaning

This does **not** target a component id directly.

It writes into `builder._data_model`, which is later serialized into a `dataModelUpdate` payload or consumed by bindings that read from the data model.

So the right mental model is:

- component id identifies a component
- `set_data(...)` seeds bound data that components may read

## `set_store(path, value, scope="page")`

Seeds client store state using slash-style paths.

Example:

```python
builder.set_store("/instance/id", 17, scope="page")
builder.set_store("/current_user/name", "alice", scope="global")
```

### Supported Scopes

Only two scopes are supported:

- `page`
- `global`

Any other scope raises:

```text
ValueError("Unsupported store scope: ...")
```

### What It Is For

Use it when your page needs initial client store state rather than surface data model state.

This distinction matters because page/global store and surface data model are different channels in the runtime.

## `set_template(name, session=None)`

Sets the template used to render the surface.

Example:

```python
builder.set_template("full", session=session)
```

### What It Actually Does

The method:

1. stores the template name
2. looks it up in the template registry
3. tries to import `sdk.templates` if needed
4. falls back to the `full` template if the requested one is missing
5. raises if neither the requested template nor `full` exists
6. stores the resolved template components and template dimensions

This is an important runtime concern, not just a cosmetic label.

## `set_surface(surface_id, shell_route=None)`

Binds the builder to a surface id and optionally a shell route.

Example:

```python
builder.set_surface("users_main", shell_route="/system/users")
```

Use this when the builder is intended for a specific mounted surface instead of the default `main`.

## Surface/Data/State Message Builders

The builder exposes a set of low-level message helpers that serialize the protocol payloads used by the runtime.

These are especially useful for effects, streams, or lower-level integration code.

### `build_surface_update_payload(surface_id="main") -> list[dict]`

Builds the raw `surfaceUpdate` payload list for all template and builder components.

### `build_surface_update(surface_id="main") -> str`

Serializes the `surfaceUpdate` payload as JSON.

### `build_data_model_update(surface_id="main", paths=None) -> str`

Serializes a `dataModelUpdate` message. If `paths` is provided, only those paths are included.

### `build_data_model_update_payload(surface_id="main", data=None) -> dict`

Builds the raw `dataModelUpdate` payload without JSON serialization.

### `build_state_update_payload(values, scope="page") -> dict`

Builds the raw `stateUpdate` payload for page/global store values.

### `build_state_patch_payload(path, action, value, scope="page") -> dict`

Builds the raw `statePatch` payload for collection values in page/global store.

### `build_delete_surface(surface_id) -> str`

Builds a `deleteSurface` message as JSON.

### Property And Collection Update Helpers

The builder also exposes:

- `build_property_update_payload(...)`
- `build_property_update(...)`
- `build_collection_append_payload(...)`
- `build_collection_prepend_payload(...)`
- `build_collection_remove_payload(...)`
- `build_collection_replace_payload(...)`

Use these when you need to describe incremental updates to component properties rather than a full rerender.

## Practical Guidance

For normal page authoring:

- prefer YAML loaded through `load(...)` for module pages
- use `set_data(...)` when your components bind to surface data
- use `set_store(...)` when the page needs page/global client state
- use component collection/property effects from actions for incremental updates
- use `Builder()` plus wrapped component constructors for generated fragments,
  previews, drawer content, or infrastructure-level UI
- use the raw payload builders only when you truly need lower-level protocol output
