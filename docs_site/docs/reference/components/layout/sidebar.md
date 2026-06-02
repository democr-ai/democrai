# Sidebar

[<- Back to Layout Components](./index.md)

## Definition

`Sidebar` marks a side region of an application layout. It is intended for navigation, filters, tools, or auxiliary content placed beside a main `ContentArea`.

## Scope

Use `Sidebar` when the page needs a structural side area with controlled width. Do not use it as a generic replacement for `Column`: when repeated content must flow predictably, put a layout container such as `Column` or `ScrollArea` inside the sidebar and update that inner container.

## Properties

| Property | Type | Default | Notes |
|---|---|---|---|
| `children` | `list[str | Component]` | `[]` | Content rendered inside the sidebar. Prefer an explicit layout container as the first child for repeated items. |
| `width` | `int | string` | client default | Sidebar width. |
| `max_width` | `int | string` | client default | Optional maximum width. |
| `padding` | `list[int]` | client default | Inner spacing used by the web renderer and shell layouts. |
| `align` | `string` | `"top"` | Alignment passed to the internal layout on web. |
| `style` | `string` | client/theme default | Common style property. |

## Static Sidebar

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="Sidebar static example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="sidebar-static-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="sidebar-static-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="sidebar-static-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>nav = sdk.ui.Column("sidebar_nav", ["nav_item_1", "nav_item_2"])
builder.add(nav)

sidebar = sdk.ui.Sidebar("sidebar", [nav.id])
sidebar.set_property("width", 220)
sidebar.set_property("max_width", 220)
builder.add(sidebar)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="sidebar-static-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Sidebar
  id: sidebar
  width: 220
  max_width: 220
  children:
    - kind: Column
      id: sidebar_nav
      children:
        - nav_item_1
        - nav_item_2</code></pre></div>
  </div>
</div>

## With ContentArea

Use `Sidebar` beside `ContentArea` to build the common side-navigation shell.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="Sidebar with ContentArea example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="sidebar-content-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="sidebar-content-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="sidebar-content-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>sidebar = sdk.ui.Sidebar("sidebar", ["sidebar_nav"])
sidebar.set_property("width", 220)
sidebar.set_property("max_width", 220)
builder.add(sidebar)

content = sdk.ui.ContentArea("content", ["content_body"])
content.set_property("stretch", True)
builder.add(content)

shell = sdk.ui.Row("page_shell", [sidebar.id, content.id])
shell.set_property("align", "fill")
shell.set_property("stretch", True)
builder.add(shell)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="sidebar-content-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Row
  id: page_shell
  align: fill
  stretch: true
  children:
    - kind: Sidebar
      id: sidebar
      width: 220
      max_width: 220
      children:
        - sidebar_nav
    - kind: ContentArea
      id: content
      stretch: true
      children:
        - content_body</code></pre></div>
  </div>
</div>

## Store Binding

Bind `width` and `max_width` when the sidebar size is driven by page state.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="Sidebar store binding example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="sidebar-store-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="sidebar-store-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="sidebar-store-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>sidebar = sdk.ui.Sidebar("sidebar_store", ["sidebar_nav"])
sidebar.set_property("width", bound.store("/components_test/sidebar/width", scope="page", default=220))
sidebar.set_property("max_width", bound.store("/components_test/sidebar/width", scope="page", default=220))
builder.add(sidebar)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="sidebar-store-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Sidebar
  id: sidebar_store
  width: {type: store, scope: page, path: /components_test/sidebar/width, default: 220}
  max_width: {type: store, scope: page, path: /components_test/sidebar/width, default: 220}
  children:
    - sidebar_nav</code></pre></div>
  </div>
</div>

## Data Model Binding

Use data-model binding when the sidebar width comes from surface data.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="Sidebar data model binding example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="sidebar-data-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="sidebar-data-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="sidebar-data-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>sidebar = sdk.ui.Sidebar("sidebar_data", ["sidebar_nav"])
sidebar.set_property("width", bound.data("/components_test/sidebar_model/width", default=220))
sidebar.set_property("max_width", bound.data("/components_test/sidebar_model/width", default=220))
builder.add(sidebar)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="sidebar-data-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Sidebar
  id: sidebar_data
  width: "@data/components_test/sidebar_model/width"
  max_width: "@data/components_test/sidebar_model/width"
  children:
    - sidebar_nav</code></pre></div>
  </div>
</div>

## Property Updates

Declare capabilities before updating `width` or `max_width` directly.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="Sidebar property update example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="sidebar-update-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="sidebar-update-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="sidebar-update-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>sidebar = sdk.ui.Sidebar("sidebar_live", ["sidebar_nav"])
sidebar.set_property("width", 220)
sidebar.set_property("max_width", 220)
sidebar.allow("width.set", "max_width.set")
builder.add(sidebar)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="sidebar-update-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Sidebar
  id: sidebar_live
  width: 220
  max_width: 220
  capabilities: [width.set, max_width.set]
  children:
    - sidebar_nav</code></pre></div>
  </div>
</div>

The action can update store, data model, and live sidebar width:

```python
return sdk.effects.respond(
    sdk.effects.ui_property_update("sidebar_live", "width", 300, surface_id=surface_id),
    sdk.effects.ui_property_update("sidebar_live", "max_width", 300, surface_id=surface_id),
)
```

## Dynamic Navigation Items

For dynamic navigation, update an inner `Column` or `ScrollArea` rather than appending repeated items directly to `Sidebar.children`.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="Sidebar dynamic children example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="sidebar-dynamic-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="sidebar-dynamic-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="sidebar-dynamic-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>nav = sdk.ui.Column("sidebar_dynamic_nav", ["nav_item_1", "nav_item_2"])
nav.allow("children.append", "children.remove")
builder.add(nav)

sidebar = sdk.ui.Sidebar("sidebar_dynamic", [nav.id])
sidebar.set_property("width", 220)
sidebar.set_property("max_width", 220)
builder.add(sidebar)

# In the action:
return sdk.effects.respond(
    sdk.effects.ui_collection_append("sidebar_dynamic_nav", "children", nav_item_dict, surface_id=surface_id),
)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="sidebar-dynamic-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Sidebar
  id: sidebar_dynamic
  width: 220
  max_width: 220
  children:
    - kind: Column
      id: sidebar_dynamic_nav
      capabilities: [children.append, children.remove]
      children:
        - kind: Text
          id: nav_item_1
          text: "Navigation item 1"
        - kind: Text
          id: nav_item_2
          text: "Navigation item 2"</code></pre></div>
  </div>
</div>

## Visibility And Permissions

`show_if`, `hide_if`, and `required_permissions` are available on `Sidebar`.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="Sidebar visibility example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="sidebar-visibility-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="sidebar-visibility-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="sidebar-visibility-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>sidebar.set_show_if({
    "conditions": [
        {"left": bound.store("/components_test/visibility/sidebar_show", scope="page", default=True), "op": "==", "right": True}
    ]
})

sidebar.set_hide_if({
    "conditions": [
        {"left": bound.store("/components_test/visibility/sidebar_hide", scope="page", default=False), "op": "==", "right": True}
    ]
})

sidebar.set_required_permissions(["components.layout.view"])</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="sidebar-visibility-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Sidebar
  id: sidebar_show_if
  show_if:
    conditions:
      - left: {type: store, scope: page, path: /components_test/visibility/sidebar_show, default: true}
        op: "=="
        right: true
  children:
    - sidebar_nav

- kind: Sidebar
  id: sidebar_hide_if
  hide_if:
    conditions:
      - left: {type: store, scope: page, path: /components_test/visibility/sidebar_hide, default: false}
        op: "=="
        right: true
  children:
    - sidebar_nav

- kind: Sidebar
  id: sidebar_required_permissions
  required_permissions: [components.layout.view]
  children:
    - sidebar_nav</code></pre></div>
  </div>
</div>

## Notes

- `Sidebar` is a structural side area, not a generic `Column` replacement.
- Put a `Column`, `ScrollArea`, or other layout container inside it when repeated content must flow predictably.
- Use `width` and `max_width` together when the sidebar should keep a fixed size.
- Use `ContentArea` beside `Sidebar` for the main workspace.
