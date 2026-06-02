# Grid

[<- Back to Complex Components](./index.md)

`Grid` is a layout container that renders its direct children in repeated columns. Children are placed left to right and continue on the next row when the current row is full.

Use it for predictable card, metric, or section layouts where the column count is part of the page structure. `Grid` does not provide drag and drop, dashboard editing, item insertion menus, widget coordinates, or per-item action context.

## Constructor

```python
Grid(
    id: str,
    children: list[str | Component] | None = None,
    columns: int = 2,
)
```

## Properties

| Property | Type | Default | Description |
|---|---:|---:|---|
| `children` | `list[str | Component]` | `[]` | Components rendered as grid cells. |
| `columns` | `int` | `2` | Number of repeated columns. |
| `style` | `str | dict` | none | Common style property applied to the grid container. |
| `visible` | `bool` | `true` | Common runtime visibility property. |
| `show_if` | condition | none | Shows the grid only when the condition is true. |
| `hide_if` | condition | none | Hides the grid when the condition is true. |
| `required_permissions` | `list[str]` | `[]` | Requires permissions before the grid is rendered. |
| `capabilities` | `list[str]` | `[]` | Declares direct runtime updates such as `style.set` or `visible.set`. |

## Basic Layout

The test page creates metric cards first, then passes them as direct children to `Grid`.

```python
cards = [
    sdk.ui.Card("kpi_revenue", [sdk.ui.Text("kpi_revenue_text", "Revenue")]),
    sdk.ui.Card("kpi_users", [sdk.ui.Text("kpi_users_text", "Users")]),
    sdk.ui.Card("kpi_latency", [sdk.ui.Text("kpi_latency_text", "Latency")]),
]

grid = sdk.ui.Grid("dashboard_grid", cards, columns=3)
grid.set_property("style", "margin-top: 4px;")
```

```yaml
- kind: Grid
  id: dashboard_grid
  columns: 3
  style: "margin-top: 4px;"
  children:
    - kind: Card
      id: kpi_revenue
      children:
        - kind: Text
          id: kpi_revenue_text
          text: Revenue
    - kind: Card
      id: kpi_users
      children:
        - kind: Text
          id: kpi_users_text
          text: Users
```

## Bindings And Updates

The demo binds `style` through page store and the surface data model. Direct updates also target `style`; the grid declares the matching `style.set` capability.

```python
store_grid = sdk.ui.Grid("store_grid", cards, columns=3)
store_grid.set_property(
    "style",
    bound.store(
        "/components_test/grid/store_style",
        scope="page",
        default="margin-top: 4px; padding: 10px; border: 1px solid transparent;",
    ),
)

data_grid = sdk.ui.Grid("data_grid", cards, columns=3)
data_grid.set_property(
    "style",
    bound.data("/components_test/grid_model/style", default="margin-top: 4px;"),
)

live_grid = sdk.ui.Grid("live_grid", cards, columns=3).allow("style.set", "visible.set")
```

```yaml
- kind: Grid
  id: store_grid
  columns: 3
  style: {type: store, scope: page, path: /components_test/grid/store_style, default: "margin-top: 4px; padding: 10px; border: 1px solid transparent;"}
  capabilities: [style.set, visible.set]
  children: [kpi_revenue, kpi_users]

- kind: Grid
  id: data_grid
  columns: 3
  style: "@data/components_test/grid_model/style"
  capabilities: [style.set, visible.set]
  children: [kpi_revenue, kpi_users]
```

A direct style update targets the current surface:

```python
return sdk.effects.respond(
    sdk.effects.ui_property_update(
        "live_grid",
        "style",
        "margin-top: 4px; padding: 10px; border: 1px solid #2563eb;",
        action="set",
        surface_id=ctx["_surface_id"],
    )
)
```

## Visibility And Permissions

`show_if`, `hide_if`, and `required_permissions` work like other components. The test page uses page-store flags for visibility and a permission requirement on the static grid.

```python
grid.set_show_if({
    "conditions": [
        {"left": bound.store("/components_test/grid/show", scope="page", default=True), "op": "==", "right": True}
    ]
})
grid.set_hide_if({
    "conditions": [
        {"left": bound.store("/components_test/grid/hide", scope="page", default=False), "op": "==", "right": True}
    ]
})
grid.set_required_permissions(["components.grid.view"])
```

```yaml
- kind: Grid
  id: guarded_grid
  columns: 2
  show_if:
    conditions:
      - left: {type: store, scope: page, path: /components_test/grid/show, default: true}
        op: "=="
        right: true
  hide_if:
    conditions:
      - left: {type: store, scope: page, path: /components_test/grid/hide, default: false}
        op: "=="
        right: true
  required_permissions: [components.grid.view]
  capabilities: [style.set, visible.set]
  children: [kpi_revenue, kpi_users]
```

## Behavior

- The web client renders `Grid` as a CSS grid with `repeat(columns, minmax(0, 1fr))`.
- The desktop client renders `Grid` with a `QGridLayout`.
- `columns` controls placement only; it does not transform children.
- `Grid` accepts normal child components and has no item data format.
