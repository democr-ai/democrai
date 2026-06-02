# Effects: UI Messages and Patching

## `ui_messages(messages)`

Use this when you already have raw UI protocol messages and want to return them as one effect.

### Real project example

Closing a drawer can be expressed as a raw UI message:

```python
return sdk.effects.respond(
    sdk.effects.ui_messages([{"deleteSurface": {"surfaceId": "drawer"}}])
)
```

## `ui_property_update(component_id, property_name, value, action="set", surface_id="main")`

Use this when one component property should change without rerendering the page.

### Real project example

```python
return module_sdk.effects.respond(
    module_sdk.effects.ui_property_update(table_id, "rows", rows, action="set"),
    module_sdk.effects.ui_property_update(table_id, "page", resolved_page),
    module_sdk.effects.ui_property_update(table_id, "page_size", resolved_page_size),
    module_sdk.effects.ui_property_update(table_id, "total_rows", total_rows),
)
```

### Value shape matters

The `value` must match the actual property contract of the component.

For example:

- a numeric property can often receive a plain number
- a boolean property can often receive a plain boolean
- a text property may need a literal or bound-value shape depending on the component contract

## `ui_collection_append(component_id, property_name, value, surface_id="main")`

Use this when one item should be appended to a collection property.

## `ui_collection_prepend(component_id, property_name, value, surface_id="main")`

Use this when one or more items should be inserted before the current collection property.

## `ui_collection_remove(component_id, property_name, value, surface_id="main")`

Use this when one item should be removed from a collection property.

## `ui_collection_replace(component_id, property_name, value, surface_id="main")`

Use this when one item in a collection property should be replaced.

Use these helpers when the component is already mounted and patch-capable.

For visible collections such as message timelines, table rows, list items, or
component children, prefer collection patches over store patches. They target
the mounted component directly and avoid forcing clients to recalculate a large
bound store value.

## `ui_state_patch(path, action, value, scope="page")`

Use this when a bound page/global store value is a collection and the client should mutate it locally.
Supported actions are `append`, `prepend`, `remove`, `replace`, and `set`.

Use state patches for small client-side state collections. Do not use them as
the primary update mechanism for large dynamic timelines, especially chat
message lists. In those cases, seed the initial visible window from backend
state and then patch the mounted collection with `ui_collection_append(...)`,
`ui_collection_prepend(...)`, `ui_collection_replace(...)`, or their streaming
counterparts.

```python
return sdk.effects.respond(
    sdk.effects.ui_state_patch(
        "/chat/messages",
        "append",
        {"id": "m_3", "role": "assistant", "kind": "text", "content": {"text": "Done."}},
        scope="page",
    )
)
```

## `build_aux_surface_messages(builder, surface_id) -> list[dict]`

Use this when you have a builder for a drawer/modal/auxiliary surface and need the complete message sequence required to mount it.

### Real project example

```python
drawer_builder = await Router.resolve("/components/overlays/drawer_sample", session)
return sdk.effects.respond(
    sdk.effects.ui_messages(
        sdk.effects.build_aux_surface_messages(drawer_builder, surface_id="drawer")
    )
)
```

## `ui_agent_commands(commands)`

Use this when you need the raw `agentUICommands` protocol payload itself.

This helper is different from the rest of the page.

It returns a transport-level message shape:

```python
{"agentUICommands": {"commands": commands}}
```

That is useful when you are already working at raw protocol level, but it is not one of the standard typed effects parsed by the normal `respond(...)` effect pipeline.

So the safe rule is:

- use `respond(...)` with `navigate`, `render`, `notify`, `ui_messages`, and the other typed effects documented in this domain
- use `ui_agent_commands(...)` only when you explicitly need the raw protocol payload and you know the receiving transport path consumes `agentUICommands`
