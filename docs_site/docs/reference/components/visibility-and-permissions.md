# Visibility And Permissions

[<- Back to Components Index](./index.md)

`show_if`, `hide_if`, and `required_permissions` are part of the shared component contract. Use them to hide or show UI elements from store values, data-model values, or the current user's permissions.

These fields can be declared on regular components. Some components also accept them inside nested specs such as row actions or item actions; in that case the rule gates only the nested element, not the parent component.

## Fields

| Field | Purpose |
|---|---|
| `show_if` | Shows the target only when the rule evaluates to `true`. |
| `hide_if` | Hides the target when the rule evaluates to `true`. |
| `required_permissions` | Shows the target only when the current user has at least one required permission. |

`required_permissions` is UI gating. It does not replace backend authorization on actions or routes.

## Evaluation

Current web and desktop renderers evaluate component visibility in this order:

1. `required_permissions`
2. `show_if`
3. `hide_if`

If the permission gate fails, the component is not rendered. If the permission gate passes, `show_if` can still hide the component, and `hide_if` can still hide it after that.

`required_permissions` uses OR semantics:

- an empty list allows the component
- a list with multiple entries requires any one matching permission
- `super` and legacy `admin` roles bypass the component-level permission list

## Rule Shape

For component-level `show_if` and `hide_if`, use a grouped rule with `conditions`. This is the portable form supported by both renderers.

```yaml
show_if:
  conditions:
    - left: {type: store, scope: page, path: /can_view, default: true}
      op: "=="
      right: true
```

Use `mode: OR` when any condition can make the rule pass. If `mode` is omitted, conditions are evaluated as `AND`.

```yaml
hide_if:
  mode: OR
  conditions:
    - left: {type: store, scope: page, path: /archived, default: false}
      op: "=="
      right: true
    - left: {type: store, scope: page, path: /locked, default: false}
      op: "=="
      right: true
```

## Operators

Use this shared operator set when the page must work on both web and desktop:

| Operator | Meaning |
|---|---|
| `==` | left equals right |
| `!=` | left differs from right |
| `>` | numeric left is greater than right |
| `<` | numeric left is less than right |
| `>=` | numeric left is greater than or equal to right |
| `<=` | numeric left is less than or equal to right |
| `in` | left is contained in right |
| `contains` | right is contained in left |

The web renderer also supports `matches`, `exists`, and `empty`. Do not use those operators for examples that must behave the same on desktop.

## Python And YAML

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="Visibility example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="visibility-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="visibility-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="visibility-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>from democrai.sdk.ui import bound

component.set_show_if({
    "conditions": [
        {
            "left": bound.store("/components_test/visibility/component_show", scope="page", default=True),
            "op": "==",
            "right": True,
        }
    ]
})

component.set_hide_if({
    "conditions": [
        {
            "left": bound.store("/components_test/visibility/component_hide", scope="page", default=False),
            "op": "==",
            "right": True,
        }
    ]
})

component.set_required_permissions(["components.content.view"])</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="visibility-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Text
  id: component_show_if
  text: "show_if visible"
  show_if:
    conditions:
      - left: {type: store, scope: page, path: /components_test/visibility/component_show, default: true}
        op: "=="
        right: true

- kind: Text
  id: component_hide_if
  text: "hide_if visible"
  hide_if:
    conditions:
      - left: {type: store, scope: page, path: /components_test/visibility/component_hide, default: false}
        op: "=="
        right: true

- kind: Text
  id: component_required_permissions
  text: "required_permissions gate"
  required_permissions: [components.content.view]</code></pre></div>
  </div>
</div>

## Binding Operands

Rule operands use the same binding payloads as component properties.

Python store binding:

```python
bound.store("/can_view", scope="page", default=True)
```

Python data-model binding:

```python
bound.data("/selection/status", default="draft")
```

YAML explicit store binding:

```yaml
left:
  type: store
  scope: page
  path: /can_view
  default: true
```

YAML compact data-model binding:

```yaml
left: "@data/selection/status"
```

Actions that toggle visibility should update the observed page or global store path with `stateUpdate`.

```python
return sdk.effects.respond(
    sdk.effects.ui_messages([
        {
            "stateUpdate": {
                "scope": "page",
                "values": {
                    "/components_test/visibility/component_show": False,
                },
            }
        }
    ])
)
```

## Nested Specs

Nested specs can use the same fields when the component exposes them. The rule applies to the nested item only.

```yaml
- kind: DataTable
  id: users_table
  rows: "@state/page/users"
  columns:
    - key: email
      label: "Email"
  row_actions:
    - label: "Suspend"
      action:
        name: users.suspend
      required_permissions: [users.user.suspend]
      show_if:
        left: "$item.status"
        op: "!="
        right: suspended
```

This rule hides the `Suspend` row action for rows that do not match. It does not hide `users_table`.

## Practical Rules

- Use `show_if` for positive visibility conditions.
- Use `hide_if` for negative guards that are easier to read directly.
- Use `required_permissions` for RBAC-driven UI gating.
- Use store bindings for visibility state changed by actions.
- Keep component-level rules in grouped `conditions` form for web and desktop parity.
