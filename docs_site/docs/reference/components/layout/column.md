# Column

[<- Back to Layout Components](./index.md)

## Definition

`Column` is the base vertical layout container. It renders its children from top to bottom.

## Scope

Use `Column` when child order must be vertical and predictable: page sections, form groups, stacked rows, navigation groups, and content blocks inside larger layout regions.

Do not use `Column` for semantic shell sections. Use `Header`, `Sidebar`, `ContentArea`, or a ready layout when the region has a specific page-shell role. Use `Row` when children should be arranged horizontally.

## Properties

| Property | Type | Default | Notes |
|---|---|---|---|
| `children` | `list[str | Component]` | `[]` | Vertical child collection. Supports append/remove patches. |
| `align` | `string` | `"top"` | Common values are `top`, `bottom`, `left`, `right`, `center`, and `fill`. |
| `style` | `string` | client default | Standard style property. |
| `padding` | `list[int]` | client default | Initial inner spacing. |
| `width` | `int | string` | client default | Optional minimum width. |
| `max_width` | `int | string` | client default | Optional maximum width. |
| `stretch` | `bool` | client default | Web layout stretch hint. Desktop columns use an expanding size policy. |

## Static Children

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="Column static example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="column-static-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="column-static-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="column-static-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>builder.add(sdk.ui.Text("column_item_1", "Column item 1"))
builder.add(sdk.ui.Text("column_item_2", "Column item 2"))
builder.add(sdk.ui.Text("column_item_3", "Column item 3"))

column = sdk.ui.Column(
    "content_stack",
    ["column_item_1", "column_item_2", "column_item_3"],
)
column.set_property("align", "top")
builder.add(column)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="column-static-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Column
  id: content_stack
  align: top
  children:
    - kind: Text
      id: column_item_1
      text: "Column item 1"
    - kind: Text
      id: column_item_2
      text: "Column item 2"
    - kind: Text
      id: column_item_3
      text: "Column item 3"</code></pre></div>
  </div>
</div>

## Store Binding

Bind `style` when a column style is controlled by page or global store state.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="Column store binding example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="column-store-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="column-store-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="column-store-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>builder.set_store("/components_test/column/style", "", scope="page")

column = sdk.ui.Column("content_stack", ["column_item_1", "column_item_2"])
column.set_property(
    "style",
    bound.store("/components_test/column/style", scope="page", default=""),
)
builder.add(column)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="column-store-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Column
  id: content_stack
  style: {type: store, scope: page, path: /components_test/column/style, default: ""}
  children:
    - column_item_1
    - column_item_2</code></pre></div>
  </div>
</div>

## Data Model Binding

Use data-model binding when the column style comes from the current surface data.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="Column data model binding example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="column-data-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="column-data-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="column-data-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>builder.set_data("/components_test/column_model/style", "")

column = sdk.ui.Column("content_stack", ["column_item_1", "column_item_2"])
column.set_property(
    "style",
    bound.data("/components_test/column_model/style", default=""),
)
builder.add(column)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="column-data-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Column
  id: content_stack
  style: "@data/components_test/column_model/style"
  children:
    - column_item_1
    - column_item_2</code></pre></div>
  </div>
</div>

## Property Updates

Declare capabilities before updating `style` directly.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="Column property update example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="column-update-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="column-update-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="column-update-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>column = sdk.ui.Column("content_stack", ["column_item_1", "column_item_2"])
column.allow("style.set")
builder.add(column)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="column-update-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Column
  id: content_stack
  capabilities: [style.set]
  children:
    - column_item_1
    - column_item_2</code></pre></div>
  </div>
</div>

The action updates store, data model, and live component state:

```python
surface_id = ctx["_surface_id"]
style = "min-height: 120px;"

return sdk.effects.respond(
    sdk.effects.ui_messages([
        {"stateUpdate": {"scope": "page", "values": {"/components_test/column/style": style}}},
        sdk.ui.Builder.build_data_model_update_payload(
            surface_id=surface_id,
            data={"components_test": {"column_model": {"style": style}}},
        ),
    ]),
    sdk.effects.ui_property_update(
        "content_stack",
        "style",
        style,
        surface_id=surface_id,
    ),
)
```

## Dynamic Children

Use collection patches for dynamic vertical content. The patch target is `children`.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="Column dynamic children example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="column-dynamic-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="column-dynamic-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="column-dynamic-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>column = sdk.ui.Column("content_stack", ["column_item_1", "column_item_2"])
column.allow("children.append", "children.remove")
builder.add(column)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="column-dynamic-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Column
  id: content_stack
  capabilities: [children.append, children.remove]
  children:
    - column_item_1
    - column_item_2</code></pre></div>
  </div>
</div>

Append and remove actions target the `children` collection:

```python
return sdk.effects.respond(
    sdk.effects.ui_collection_append(
        "content_stack",
        "children",
        sdk.ui.Text("column_item_3", "Column item 3").to_dict(),
        surface_id=ctx["_surface_id"],
    ),
    sdk.effects.ui_collection_remove(
        "content_stack",
        "children",
        {"id": "column_item_3"},
        surface_id=ctx["_surface_id"],
    ),
)
```

## Visibility And Permissions

`show_if`, `hide_if`, and `required_permissions` are available on `Column`.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="Column visibility example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="column-visibility-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="column-visibility-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="column-visibility-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>column.set_show_if({
    "conditions": [
        {"left": bound.store("/components_test/visibility/column_show", scope="page", default=True), "op": "==", "right": True}
    ]
})

column.set_hide_if({
    "conditions": [
        {"left": bound.store("/components_test/visibility/column_hide", scope="page", default=False), "op": "==", "right": True}
    ]
})

column.set_required_permissions(["components.layout.view"])</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="column-visibility-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Column
  id: column_show_if
  show_if:
    conditions:
      - left: {type: store, scope: page, path: /components_test/visibility/column_show, default: true}
        op: "=="
        right: true
  children:
    - column_item_1

- kind: Column
  id: column_hide_if
  hide_if:
    conditions:
      - left: {type: store, scope: page, path: /components_test/visibility/column_hide, default: false}
        op: "=="
        right: true
  children:
    - column_item_1

- kind: Column
  id: column_required_permissions
  required_permissions: [components.layout.view]
  children:
    - column_item_1</code></pre></div>
  </div>
</div>

## Notes

- Put repeated vertical content directly in `Column.children`.
- Use `children.append` and `children.remove` for incremental vertical lists.
- Use `Row` inside a `Column` when one section needs horizontal content.
- Use semantic layout components instead of `Column` when the region represents a header, sidebar, content area, or surface host.
