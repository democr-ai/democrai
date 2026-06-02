# UI Builder and A2UI: Builder Methods

## Component Management

### `add(component)`

Adds a component to the builder.

Example:

```python
builder = sdk.ui.Builder()
builder.add(
    sdk.ui.Text("title", "Users")
)
builder.add(
    sdk.ui.Button("refresh_btn", label="Refresh", action="demo.users.reload")
)
```

### `get_component(component_id)`

Returns a component by id if it is managed by the builder.

Example:

```python
title = builder.get_component("title")
if title is not None:
    title.set_property("text", "Active Users")
```

This is an API method, not the preferred population pattern for module pages.

For YAML-authored module views, declare the component property as a binding and
seed the value with `builder.set_data(...)` or `builder.set_store(...)` from the
render function. Reach for `get_component(...).set_property(...)` only when the
value cannot reasonably be expressed through YAML/binding, or when you are
building low-level UI tooling rather than a normal module page.

### `get_roots()`

Returns the root components of the surface, excluding components referenced as children of other components.

Example:

```python
builder = sdk.ui.Builder()
builder.add(
    sdk.ui.Column(
        "page_root",
        children=["title", "refresh_btn"],
    )
)
builder.add(sdk.ui.Text("title", "Users"))
builder.add(sdk.ui.Button("refresh_btn", label="Refresh", action="demo.users.reload"))

roots = builder.get_roots()
# roots contains only the "page_root" component
```

### `snapshot(include_components=True, component_serializer=None) -> dict`

Returns a serializable snapshot of the builder transport state.

The snapshot includes:

- surface data model
- page/global store seed data
- template metadata
- surface id and shell route
- components, unless `include_components=False`

Example:

```python
builder = sdk.ui.Builder()
builder.set_surface("users_main", shell_route="/system/users")
builder.set_template("full", session=session)
builder.set_data("/filters/search", "")
builder.set_store("/users/selected_id", None, scope="page")
builder.add(sdk.ui.Text("title", "Users"))

payload = builder.snapshot()
```

Use this when a builder must cross a boundary where the original Python objects should not be kept directly, for example runtime handoff, deferred rendering, or helper code that needs a complete transport snapshot.

If the consumer already has component dictionaries or does not need components, pass `include_components=False`:

```python
state_payload = builder.snapshot(include_components=False)
```

### `merge(source, components=False, metadata=False, replace=False, component_factory=None)`

Merges builder transport state from another builder or from a snapshot dictionary.

By default, `merge(...)` merges only data model and store seed data. Components and metadata are opt-in so callers do not accidentally duplicate component trees or overwrite the target surface configuration.

Example: enrich a YAML-loaded builder with runtime state from another builder:

```python
page = sdk.ui.load("ui/yaml/users_list")

state = sdk.ui.Builder()
state.set_data("/filters/status", "active")
state.set_store("/users/loading", False, scope="page")

page.merge(state)
```

Example: copy structure and state into an empty builder:

```python
source = sdk.ui.load("ui/yaml/users_list")
source.set_data("/filters/search", "")
source.set_store("/users/page", 1, scope="page")

target = sdk.ui.Builder()
target.merge(source, components=True)
```

Use `metadata=True` when the target should also inherit template, surface id, dimensions, template components, and shell route:

```python
target.merge(source, components=True, metadata=True)
```

Use `replace=True` when the target builder should be overwritten rather than merged:

```python
target.merge(source.snapshot(), components=True, metadata=True, replace=True)
```

When merging a snapshot that contains serialized component dictionaries, `component_factory` can convert each dictionary back into the object shape expected by the caller:

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

## Builder Composition Helpers

### `merge_builders(base_builder, extra_builder) -> None`

Merges builder state from `extra_builder` into `base_builder` and appends only components whose ids are not already present in the base builder.

Example:

```python
from democrai.sdk.ui import merge_builders

page = sdk.ui.load("ui/yaml/user_detail")

header = sdk.ui.Builder()
header.add(sdk.ui.Title("user_title", "User detail", level=2))
header.set_store("/user/sidebar_open", True, scope="page")

merge_builders(page, header)
```

Use this helper when separate helper functions build small component groups and the final page must collect them without duplicating ids.

For more explicit control over components, metadata, and replace semantics, prefer `Builder.merge(...)`.

## Data Model Methods

### `set_data(path, value)`

Sets a value in the surface data model using slash notation.

Example:

```python
builder.set_data("/user/name", "Fabio")
```

Another practical example:

```python
builder.set_data("/table/rows", [{"id": 1, "name": "Anna"}])
builder.set_data("/table/total", 1)
```

### `set_store(path, value, scope="page")`

Seeds client store state using slash notation.

Use this for reactive page/global state that components read through `@state/...` or `bound.store(...)`.

Example:

```python
builder.set_store("/draft_title", "", scope="page")
builder.set_store("/current_path", "/users/index", scope="global")
```

## Template and Surface

### `set_template(name, session=None)`

Sets the template used to render the surface.

Example:

```python
builder = sdk.ui.Builder()
builder.set_template("full", session=session)
```

Use this before generating the final surface payload when the page must mount inside a known application template.

### `set_surface(surface_id, shell_route=None)`

Binds the builder to a surface id and optional shell route.

Example:

```python
builder.set_surface("users_main", shell_route="/demo/users")
```

## Protocol Generation

### `build_data_model_update(surface_id="main", paths=None) -> str`

### `build_data_model_update_payload(surface_id="main", data=None) -> dict`

Build the data-model update message.

Full snapshot example:

```python
builder = sdk.ui.Builder()
builder.set_data("/filters/search", "anna")
builder.set_data("/filters/status", "active")

payload = builder.build_data_model_update_payload(surface_id="users_main", data={
    "filters": {
        "search": "anna",
        "status": "active",
    }
})
```

Result shape:

```python
{
    "dataModelUpdate": {
        "surfaceId": "users_main",
        "data": {
            "filters": {
                "search": "anna",
                "status": "active",
            }
        },
    }
}
```

Scoped-path example using the builder state:

```python
builder.set_data("/filters/search", "anna")
builder.set_data("/filters/status", "active")

message = builder.build_data_model_update(
    surface_id="users_main",
    paths=["/filters/search"],
)
```

### `build_state_update_payload(values, scope="page") -> dict`

Builds a `stateUpdate` payload for client store values.

Example:

```python
payload = sdk.ui.Builder.build_state_update_payload(
    {"/draft_title": "Anna"},
    scope="page",
)
```

### `build_state_patch_payload(path, action, value, scope="page") -> dict`

Builds a `statePatch` payload for collection values in page/global client store.

Supported actions are `append`, `prepend`, `remove`, `replace`, and `set`.

Example:

```python
payload = sdk.ui.Builder.build_state_patch_payload(
    "/chat/messages",
    "append",
    {"id": "m_3", "role": "assistant", "kind": "text"},
    scope="page",
)
```

### `build_surface_update_payload(surface_id="main") -> list[dict]`

### `build_surface_update(surface_id="main") -> str`

Build the serialized surface update message.

Example:

```python
builder = sdk.ui.Builder()
builder.set_template("full", session=session)
builder.set_surface("users_main")
builder.add(sdk.ui.Text("title", "Users"))

payload = builder.build_surface_update_payload("users_main")
message = builder.build_surface_update("users_main")
```

Use this for the initial mount or when rebuilding the whole surface structure is the right operation.

### `build_delete_surface(surface_id) -> str`

Build the delete-surface message.

Example:

```python
message = sdk.ui.Builder.build_delete_surface("users_main")
```

Use it when the surface should be explicitly removed from connected clients.

### `build_property_update_payload(component_id, property_name, value, action="set", surface_id="main") -> dict`

### `build_property_update(...) -> str`

Build a property update message.

Example:

```python
payload = sdk.ui.Builder.build_property_update_payload(
    component_id="status_badge",
    property_name="text",
    value="Synced",
    surface_id="users_main",
)

message = builder.build_property_update(
    component_id="status_badge",
    property_name="variant",
    value="success",
    surface_id="users_main",
)
```

Use this when the component is already mounted and only one property must change.

### `build_collection_append_payload(...)`

### `build_collection_prepend_payload(...)`

### `build_collection_remove_payload(...)`

### `build_collection_replace_payload(...)`

Build collection mutation messages for append/prepend/remove/replace flows.

Append example:

```python
payload = sdk.ui.Builder.build_collection_append_payload(
    component_id="users_table",
    property_name="rows",
    value={"id": 2, "name": "Marco"},
    surface_id="users_main",
)
```

Remove example:

```python
payload = sdk.ui.Builder.build_collection_remove_payload(
    component_id="users_table",
    property_name="rows",
    value={"id": 2, "name": "Marco"},
    surface_id="users_main",
)
```

Replace example:

```python
payload = sdk.ui.Builder.build_collection_replace_payload(
    component_id="users_table",
    property_name="rows",
    value=[
        {"id": 1, "name": "Anna"},
        {"id": 2, "name": "Marco"},
    ],
    surface_id="users_main",
)
```

Use these only when the target component exposes the corresponding capability for that collection property.
