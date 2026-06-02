# Common Component Properties

This page documents cross-component properties that are not tied to a specific domain.

## Visibility and Access

| Property | How to set it in Python | YAML placement |
|---|---|---|
| `required_permissions` | `component.set_required_permissions([...])` | under component props |
| `show_if` | `component.set_show_if(rule)` | under component props |
| `hide_if` | `component.set_hide_if(rule)` | under component props |

See [Visibility And Permissions](visibility-and-permissions.md) for the full rule contract, binding examples, renderer notes, and nested-spec usage.

## Interaction and Runtime

| Property | How to set it in Python | YAML placement |
|---|---|---|
| `action` | `component.set_action("module.action", context={...})` | `action: {name: ..., context: {...}}` |
| `onChangeAction` + `onChangeMode` | `component.set_on_change_action("module.action", mode="local")` | `onChangeAction`, `onChangeMode` |
| `track_loading` | `component.track_loading("module.action")` | `track_loading` |
| `collect_input_ids` | `component.collect_input_ids("field_a", "field_b")` | `collect_input_ids` |
| `error` | `component.set_error("...")` | `error` |
| `auto_refresh` + `on_refresh` | `component.set_auto_refresh(20, "module.refresh")` | `auto_refresh`, `on_refresh` |

## Capabilities API

| Method | Effect |
|---|---|
| `set_capabilities([...])` | Replaces the exposed capabilities list |
| `allow("prop.set", ...)` | Adds capability entries |
| `deny("prop.set", ...)` | Denies capability entries |
| `mutable_value("value")` | Adds `value.set` + `value.append` |
| `mutable_collection("rows")` | Adds `rows.set/append/remove/replace` |
| `interactive()` | Adds `visible.set` + `enabled.set` |

## Complete Example (Python)

```python
import sdk

field = sdk.ui.TextField(
    id="username",
    label="Username",
    value="",
    placeholder="Type username",
)

field.set_required_permissions(["system.user.update"])
field.set_show_if({
    "mode": "AND",
    "conditions": [
        {
            "left": {"type": "store", "scope": "page", "path": "/can_edit"},
            "op": "==",
            "right": True,
        }
    ],
})
field.set_hide_if({
    "mode": "OR",
    "conditions": [
        {
            "left": {"type": "store", "scope": "page", "path": "/is_archived"},
            "op": "==",
            "right": True,
        }
    ],
})
field.set_on_change_action("users.filter", mode="search")
field.track_loading("users.filter")
field.allow("value.set", "visible.set", "enabled.set")
```

## Complete Example (YAML)

```yaml
- kind: TextField
  id: username
  label: "Username"
  value: ""
  placeholder: "Type username"
  required_permissions: ["system.user.update"]
  show_if:
    mode: AND
    conditions:
      - left:
          type: store
          scope: page
          path: /can_edit
        op: "=="
        right: true
  hide_if:
    mode: OR
    conditions:
      - left:
          type: store
          scope: page
          path: /is_archived
        op: "=="
        right: true
  onChangeAction:
    name: users.filter
    context:
      source: users_table
  onChangeMode: search
  track_loading: users.filter
  capabilities:
    - value.set
    - visible.set
    - enabled.set
```
