# Row

[<- Back to Layout Components](./index.md)

## Definition

`Row` is the base horizontal layout container. It renders its children side by side.

## Scope

Use `Row` for toolbars, inline controls, action groups, metadata bars, and side-by-side layout sections.

Do not use `Row` for vertical stacks. Use `Column` when children must be arranged top to bottom. Use semantic layout components when the region represents a page shell section such as a header, sidebar, or content area.

## Properties

| Property | Type | Default | Notes |
|---|---|---|---|
| `children` | `list[str | Component]` | `[]` | Horizontal child collection. Supports append/remove patches. |
| `align` | `string` | `"left"` desktop, `"top"` web | Common values are `left`, `center`, `right`, `top`, `bottom`, and `fill`. |
| `spacing` | `int` | `0` | Gap between children. Supports binding and direct updates. |
| `style` | `string` | client default | Standard style property. |
| `padding` | `list[int]` | client default | Web renderer padding. |
| `width` | `int | string` | client default | Optional fixed width on desktop. |
| `height` | `int | string` | client default | Optional fixed height on desktop. |
| `stretch` | `bool` | client default | Web layout stretch hint. Desktop rows use an expanding size policy. |

## Static Children

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="Row static example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="row-static-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="row-static-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="row-static-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>builder.add(sdk.ui.Button("row_action_1", "Action 1", variant="default"))
builder.add(sdk.ui.Button("row_action_2", "Action 2", variant="default"))
builder.add(sdk.ui.Button("row_action_3", "Action 3", variant="default"))

row = sdk.ui.Row(
    "toolbar",
    ["row_action_1", "row_action_2", "row_action_3"],
)
row.set_property("align", "left")
row.set_property("spacing", 8)
builder.add(row)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="row-static-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Row
  id: toolbar
  align: left
  spacing: 8
  children:
    - kind: Button
      id: row_action_1
      label: "Action 1"
      variant: default
    - kind: Button
      id: row_action_2
      label: "Action 2"
      variant: default
    - kind: Button
      id: row_action_3
      label: "Action 3"
      variant: default</code></pre></div>
  </div>
</div>

## Store Binding

Bind `spacing` when the row gap is controlled by page or global store state.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="Row store binding example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="row-store-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="row-store-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="row-store-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>builder.set_store("/components_test/row/spacing", 8, scope="page")

row = sdk.ui.Row("toolbar", ["row_action_1", "row_action_2"])
row.set_property(
    "spacing",
    bound.store("/components_test/row/spacing", scope="page", default=8),
)
builder.add(row)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="row-store-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Row
  id: toolbar
  spacing: {type: store, scope: page, path: /components_test/row/spacing, default: 8}
  children:
    - row_action_1
    - row_action_2</code></pre></div>
  </div>
</div>

## Data Model Binding

Use data-model binding when the row spacing comes from the current surface data.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="Row data model binding example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="row-data-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="row-data-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="row-data-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>builder.set_data("/components_test/row_model/spacing", 8)

row = sdk.ui.Row("toolbar", ["row_action_1", "row_action_2"])
row.set_property(
    "spacing",
    bound.data("/components_test/row_model/spacing", default=8),
)
builder.add(row)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="row-data-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Row
  id: toolbar
  spacing: "@data/components_test/row_model/spacing"
  children:
    - row_action_1
    - row_action_2</code></pre></div>
  </div>
</div>

## Property Updates

Declare capabilities before updating `spacing` directly.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="Row property update example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="row-update-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="row-update-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="row-update-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>row = sdk.ui.Row("toolbar", ["row_action_1", "row_action_2"])
row.set_property("spacing", 8)
row.allow("spacing.set")
builder.add(row)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="row-update-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Row
  id: toolbar
  spacing: 8
  capabilities: [spacing.set]
  children:
    - row_action_1
    - row_action_2</code></pre></div>
  </div>
</div>

The action updates store, data model, and live component state:

```python
surface_id = ctx["_surface_id"]
spacing = 20

return sdk.effects.respond(
    sdk.effects.ui_messages([
        {"stateUpdate": {"scope": "page", "values": {"/components_test/row/spacing": spacing}}},
        sdk.ui.Builder.build_data_model_update_payload(
            surface_id=surface_id,
            data={"components_test": {"row_model": {"spacing": spacing}}},
        ),
    ]),
    sdk.effects.ui_property_update(
        "toolbar",
        "spacing",
        spacing,
        surface_id=surface_id,
    ),
)
```

## Dynamic Children

Use collection patches for dynamic horizontal content. The patch target is `children`.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="Row dynamic children example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="row-dynamic-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="row-dynamic-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="row-dynamic-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>row = sdk.ui.Row("toolbar", ["row_action_1", "row_action_2"])
row.allow("children.append", "children.remove")
builder.add(row)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="row-dynamic-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Row
  id: toolbar
  capabilities: [children.append, children.remove]
  children:
    - row_action_1
    - row_action_2</code></pre></div>
  </div>
</div>

Append and remove actions target the `children` collection:

```python
return sdk.effects.respond(
    sdk.effects.ui_collection_append(
        "toolbar",
        "children",
        sdk.ui.Button("row_action_3", "Action 3", variant="default").to_dict(),
        surface_id=ctx["_surface_id"],
    ),
    sdk.effects.ui_collection_remove(
        "toolbar",
        "children",
        {"id": "row_action_3"},
        surface_id=ctx["_surface_id"],
    ),
)
```

## Visibility And Permissions

`show_if`, `hide_if`, and `required_permissions` are available on `Row`.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="Row visibility example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="row-visibility-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="row-visibility-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="row-visibility-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>row.set_show_if({
    "conditions": [
        {"left": bound.store("/components_test/visibility/row_show", scope="page", default=True), "op": "==", "right": True}
    ]
})

row.set_hide_if({
    "conditions": [
        {"left": bound.store("/components_test/visibility/row_hide", scope="page", default=False), "op": "==", "right": True}
    ]
})

row.set_required_permissions(["components.layout.view"])</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="row-visibility-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Row
  id: row_show_if
  show_if:
    conditions:
      - left: {type: store, scope: page, path: /components_test/visibility/row_show, default: true}
        op: "=="
        right: true
  children:
    - row_action_1

- kind: Row
  id: row_hide_if
  hide_if:
    conditions:
      - left: {type: store, scope: page, path: /components_test/visibility/row_hide, default: false}
        op: "=="
        right: true
  children:
    - row_action_1

- kind: Row
  id: row_required_permissions
  required_permissions: [components.layout.view]
  children:
    - row_action_1</code></pre></div>
  </div>
</div>

## Notes

- Put inline controls and side-by-side sections directly in `Row.children`.
- Use `children.append` and `children.remove` for incremental horizontal lists.
- Use `Column` inside a `Row` when one horizontal section needs vertical content.
- Use `spacing` for the gap between children when the gap must be explicit or dynamic.
