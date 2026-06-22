# Effects: Streams and Runtime Effects

## Live Stream Publishing

These methods are the asynchronous counterparts of the UI message helpers.

Use them when the original action is no longer the delivery vehicle for UI updates.

## `publish_to_stream(stream_id, data)`

Use this to broadcast arbitrary data to a runtime stream.

Mounted `StreamBinding` components can consume these events and convert them
into page/global store updates for the client that mounted the binding.
When a binding uses a transformer action, the action receives the mounted
client `stream_id` and can call `ask_current_store_value(...)` to merge the
incoming event with current client-held state before returning the next value.

The core runtime also publishes node resource samples to
`system.runtime.metrics.events` with `event_name` set to
`runtime.metrics.sample`.

## `publish_ui_message(stream_id, message)`

Use this when you already have a complete UI protocol message and want to push it to a stream.

## `publish_property_update(...)`

Use this when one mounted component property should change on already connected clients.

## `publish_collection_append(...)`

Use this when a collection item should be appended live through the stream.

## `publish_collection_prepend(...)`

Use this when collection items should be inserted before the current live collection.

## `publish_collection_remove(...)`

Use this when a collection item should be removed live through the stream.

## `publish_collection_replace(...)`

Use this when one collection item should be replaced live through the stream.

## `publish_state_patch(...)`

Use this when a page/global store path is bound to the UI and the client should mutate that collection locally.
Supported actions are `append`, `prepend`, `remove`, `replace`, and `set`.

Use streamed collection updates for mounted dynamic UI. A long chat timeline,
task feed, or live table should receive `publish_collection_append(...)`,
`publish_collection_prepend(...)`, or `publish_collection_replace(...)` against
the component property that renders the collection. Reserve
`publish_state_patch(...)` for small client-side store collections where the
store itself is the UI contract.

### Real project examples

```python
await module_sdk.effects.publish_collection_append(
    stream_id,
    f"chat_thread_messages_{conversation_id}",
    "messages",
    payload,
)
```

and:

```python
await module_sdk.effects.publish_property_update(
    stream_id,
    "engine_install_progress",
    "value",
    75,
    surface_id="modal",
)
```

## Client Runtime State Queries

These methods ask the client that owns a stream for its current runtime state.

Use them only from async code.
They wait for a client response and return the value sent back by that client.

If `stream_id` is `None`, the SDK uses the current request stream when one is available.
Passing the explicit `stream_id` is clearer when the action already received it in the context.

These methods read client-held runtime state.
They are not a replacement for persisted server state, and they should not be used to make domain persistence decisions that require a server-side source of truth.

## `ask_client(stream_id, query, timeout=5.0)`

Use this low-level method when you need to send a supported client-state query
directly.

```python
value = await module_sdk.effects.ask_client(
    stream_id,
    {"kind": "store_value", "path": "/filters", "scope": "page"},
)
```

If `stream_id` is `None`, the SDK tries to use the current request stream. If no
stream can be resolved, it raises `ValueError("stream_id is required")`.

Prefer the narrower helpers below when they match the data you need. They build
the query payload for the supported client-state shapes.

## `ask_current_store_value(stream_id, store_key, store_type="auto", timeout=5.0)`

Use this to read a value from the client store.

`store_type` can be:

- `page`
- `global`
- `auto`

### Example

```python
current_items = await module_sdk.effects.ask_current_store_value(
    stream_id,
    "/components_demo/items",
    "page",
)
```

## `ask_current_data_value(stream_id, path, surface_id="main", timeout=5.0)`

Use this to read a value from the client data model for one surface.

### Example

```python
selected_row = await module_sdk.effects.ask_current_data_value(
    stream_id,
    "/table/selected_row",
    surface_id="main",
)
```

## `ask_current_component_props(stream_id, component_id, surface_id="main", timeout=5.0)`

Use this to read the current protocol props for one component.

This returns the component props tracked by the client runtime tree.
It does not introspect private widget or DOM state.

### Example

```python
props = await module_sdk.effects.ask_current_component_props(
    stream_id,
    "results_table",
    surface_id="main",
)
rows = props.get("rows", []) if isinstance(props, dict) else []
```

## `ask_current_component(stream_id, component_id, surface_id="main", timeout=5.0)`

Use this to read the full protocol component node for one component.

This includes the component wrapper and any tracked children metadata.

## `ask_current_surface_tree(stream_id, surface_id="main", timeout=5.0)`

Use this to read the full client-side protocol tree for one surface.

Prefer narrower methods when you only need one store key, data path, or component.

## Runtime and Window Effects

## `pipeline(task, label, args=None, module=None)`

Use this when the action should request pipeline execution as an effect.

## `scroll(component_id)`

Use this when the client should scroll to a component.

## `refresh_modules()`

Use this when the runtime/client should refresh module state.

## `set_jwt(token)`

Use this when the client token should be replaced.

## `copy_to_clipboard(text)`

Use this when the client should copy a string to the clipboard.

## `open_url(url, download=False, filename="")`

Use this when the client should open a URL or trigger a download.
