# Binding, Store, and Capabilities

[<- Back to Components Index](./index.md)

This page describes the shared binding and update contract used by component pages.

## Python Bindings

Use `bound.store(...)` for page or global store values.

```python
from democrai.sdk.ui import bound

title = bound.store("/draft/title", scope="page", default="")
theme = bound.store("/theme", scope="global", default="dark")
current_path = bound.store("/current_path", scope="auto", default="/")
```

Use `bound.data(...)` for the current surface data model.

```python
rows = bound.data("/components_test/table_model/rows", default=[])
```

Use `bound.literal(...)` when a value must stay literal even if it looks like binding syntax.

```python
label = bound.literal("@state/page/title")
```

Use `bound.action(...)` for client-resolved action values.

```python
items = bound.action(
    "components.load_items",
    args={"limit": 20},
    default=[],
    cache_scope="page",
)
```

## YAML Bindings

Compact store bindings:

```yaml
- kind: Text
  id: draft_title
  text: "@state/page/draft/title"
```

Store scopes:

| YAML | Python equivalent |
|---|---|
| `@state/page/path` | `bound.store("path", scope="page")` |
| `@state/global/path` | `bound.store("path", scope="global")` |
| `@state/path` | `bound.store("path", scope="auto")` |

Data-model binding:

```yaml
- kind: Breadcrumb
  id: page_breadcrumb
  segments: "@data/components_test/breadcrumb_model/segments"
```

Explicit store binding:

```yaml
- kind: Text
  id: draft_title
  text:
    type: store
    scope: page
    path: /draft/title
    default: ""
```

Other compact forms:

| YAML | Meaning |
|---|---|
| `@action/name` | Action-bound value. |
| `@literal/value` | Literal value. |
| `@t/module.key` | Translation key resolved while parsing YAML. |
| `@tag/name` | Runtime tag constant when supported. |

## Store Updates

Actions update store values with a `stateUpdate` message.

```python
return sdk.effects.respond(
    sdk.effects.ui_messages([
        {
            "stateUpdate": {
                "scope": "page",
                "values": {
                    "/components_test/breadcrumb/segments": segments,
                },
            }
        }
    ])
)
```

Use `scope: "global"` only when the value is intentionally shared across pages or modules.

## Data Model Updates

Actions update the surface data model with `build_data_model_update_payload(...)`.

```python
surface_id = ctx["_surface_id"]

return sdk.effects.respond(
    sdk.effects.ui_messages([
        sdk.ui.Builder.build_data_model_update_payload(
            surface_id=surface_id,
            data={
                "components_test": {
                    "breadcrumb_model": {
                        "segments": segments,
                    }
                }
            },
        )
    ])
)
```

Always use the action surface id when updating data for the current surface.

## Property Updates

Direct component updates use `ui_property_update(...)`.

```python
surface_id = ctx["_surface_id"]

return sdk.effects.respond(
    sdk.effects.ui_property_update(
        "page_breadcrumb",
        "segments",
        segments,
        surface_id=surface_id,
    )
)
```

Declare the matching capability on the component.

```python
breadcrumb.allow("segments.set")
```

```yaml
- kind: Breadcrumb
  id: page_breadcrumb
  capabilities: [segments.set]
```

## Collection Updates

Collection helpers are property updates with collection actions.

```python
return sdk.effects.respond(
    sdk.effects.ui_collection_append(
        "content_stack",
        "children",
        sdk.ui.Text("item_2", "Item 2").to_dict(),
        surface_id=ctx["_surface_id"],
    ),
    sdk.effects.ui_collection_remove(
        "content_stack",
        "children",
        {"id": "item_2"},
        surface_id=ctx["_surface_id"],
    ),
)
```

Declare collection capabilities on the target component.

```python
column.allow("children.append", "children.remove")
```

```yaml
- kind: Column
  id: content_stack
  capabilities: [children.append, children.remove]
```

## Visibility Rules

`show_if` and `hide_if` use the same binding payloads.

```python
component.set_show_if({
    "conditions": [
        {
            "left": bound.store("/can_view", scope="page", default=True),
            "op": "==",
            "right": True,
        }
    ]
})
```

```yaml
show_if:
  conditions:
    - left: {type: store, scope: page, path: /can_view, default: true}
      op: "=="
      right: true
```

Use `required_permissions` for RBAC visibility.

```python
component.set_required_permissions(["components.content.view"])
```

```yaml
required_permissions: [components.content.view]
```

## Practical Rules

- Bind to store for UI state that can be shared or changed by actions.
- Bind to the data model for data that belongs to a specific surface.
- Declare capabilities for every direct property or collection mutation.
- Use `ctx["_surface_id"]` for property updates and data model updates from actions.
- Do not document a binding or update pattern for a component until the Python and YAML examples are reproducible in the `components` module test page.
