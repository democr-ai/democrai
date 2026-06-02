# ScrollArea

[<- Back to Layout Components](./index.md)

## Definition

`ScrollArea` creates a bounded viewport with internal scrolling. It is a layout container: its `children` render inside the scrollable content widget.

## Scope

Use `ScrollArea` when overflow must stay inside a sidebar, content body, split pane, drawer, or any bounded layout section. Do not use it as a page-height replacement: the parent layout must still provide bounded height with properties such as `stretch`, `height`, or `min-height: 0`.

## Properties

| Property | Type | Default | Notes |
|---|---|---|---|
| `children` | `list[str | Component]` | `[]` | Content rendered inside the scroll viewport. Runtime append/remove is supported. |
| `stretch` | `bool` | `false` | Lets the scroll area fill available flex space. |
| `style` | `string` | `None` | Style applied to the scroll viewport. Supports direct property updates. |
| `content_style` | `string` | `None` | Style applied to the inner content widget. |
| `transparent` | `bool` | `false` | Makes the scroll viewport background transparent. |
| `scroll_x` | `bool` | `true` | Enables horizontal scroll when content overflows. |
| `scroll_y` | `bool` | `true` | Enables vertical scroll when content overflows. |
| `content_vertical_policy` | `string` | `"expanding"` | Desktop content sizing policy. Use `"maximum"` when content should keep natural height. |

## Static ScrollArea

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="ScrollArea static example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="scrollarea-static-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="scrollarea-static-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="scrollarea-static-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>content = sdk.ui.Column("scrollarea_content", ["row_1", "row_2"])
builder.add(content)

scroll = sdk.ui.ScrollArea("scrollarea", [content.id])
scroll.set_property("stretch", True)
scroll.set_property("scroll_x", False)
builder.add(scroll)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="scrollarea-static-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: ScrollArea
  id: scrollarea
  stretch: true
  scroll_x: false
  children:
    - kind: Column
      id: scrollarea_content
      children:
        - row_1
        - row_2</code></pre></div>
  </div>
</div>

## Store Binding

Bind `style` when viewport styling is driven by client state.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="ScrollArea store binding example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="scrollarea-store-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="scrollarea-store-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="scrollarea-store-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>scroll = sdk.ui.ScrollArea("scrollarea_store", [content.id])
scroll.set_property("stretch", True)
scroll.set_property("scroll_x", False)
scroll.set_property(
    "style",
    bound.store("/components_test/scrollarea/style", scope="page", default=""),
)
builder.add(scroll)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="scrollarea-store-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: ScrollArea
  id: scrollarea_store
  stretch: true
  scroll_x: false
  style: {type: store, scope: page, path: /components_test/scrollarea/style, default: ""}
  children:
    - scrollarea_content</code></pre></div>
  </div>
</div>

## Data Model Binding

Use data-model binding when the viewport style comes from the surface data model.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="ScrollArea data model binding example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="scrollarea-data-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="scrollarea-data-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="scrollarea-data-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>scroll = sdk.ui.ScrollArea("scrollarea_data", [content.id])
scroll.set_property("stretch", True)
scroll.set_property("scroll_x", False)
scroll.set_property(
    "style",
    bound.data("/components_test/scrollarea_model/style", default=""),
)
builder.add(scroll)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="scrollarea-data-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: ScrollArea
  id: scrollarea_data
  stretch: true
  scroll_x: false
  style: "@data/components_test/scrollarea_model/style"
  children:
    - scrollarea_content</code></pre></div>
  </div>
</div>

## Property Updates

Declare capabilities before updating `style` directly.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="ScrollArea property update example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="scrollarea-update-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="scrollarea-update-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="scrollarea-update-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>scroll = sdk.ui.ScrollArea("scrollarea_live", [content.id])
scroll.set_property("stretch", True)
scroll.set_property("scroll_x", False)
scroll.allow("style.set")
builder.add(scroll)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="scrollarea-update-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: ScrollArea
  id: scrollarea_live
  stretch: true
  scroll_x: false
  capabilities: [style.set]
  children:
    - scrollarea_content</code></pre></div>
  </div>
</div>

The action can update store, data model, and the live component:

```python
return sdk.effects.respond(
    sdk.effects.ui_property_update("scrollarea_live", "style", next_style, surface_id=surface_id),
)
```

## Dynamic Children

`children` supports append and remove updates. This is useful for feeds, logs, and growing content lists.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="ScrollArea dynamic children example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="scrollarea-dynamic-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="scrollarea-dynamic-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="scrollarea-dynamic-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>scroll = sdk.ui.ScrollArea("scrollarea_dynamic", ["row_1", "row_2"])
scroll.set_property("stretch", True)
scroll.set_property("scroll_x", False)
scroll.allow("children.append", "children.remove")
builder.add(scroll)

# In the action:
return sdk.effects.respond(
    sdk.effects.ui_collection_append("scrollarea_dynamic", "children", row_component_dict, surface_id=surface_id),
)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="scrollarea-dynamic-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: ScrollArea
  id: scrollarea_dynamic
  stretch: true
  scroll_x: false
  capabilities: [children.append, children.remove]
  children:
    - kind: Text
      id: scrollarea_dynamic_row_1
      text: "Dynamic row 1"
    - kind: Text
      id: scrollarea_dynamic_row_2
      text: "Dynamic row 2"</code></pre></div>
  </div>
</div>

## Visibility And Permissions

`show_if`, `hide_if`, and `required_permissions` are available on `ScrollArea`.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="ScrollArea visibility example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="scrollarea-visibility-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="scrollarea-visibility-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="scrollarea-visibility-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>scroll.set_show_if({
    "conditions": [
        {"left": bound.store("/components_test/visibility/scrollarea_show", scope="page", default=True), "op": "==", "right": True}
    ]
})

scroll.set_hide_if({
    "conditions": [
        {"left": bound.store("/components_test/visibility/scrollarea_hide", scope="page", default=False), "op": "==", "right": True}
    ]
})

scroll.set_required_permissions(["components.layout.view"])</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="scrollarea-visibility-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: ScrollArea
  id: scrollarea_show_if
  show_if:
    conditions:
      - left: {type: store, scope: page, path: /components_test/visibility/scrollarea_show, default: true}
        op: "=="
        right: true
  children: []

- kind: ScrollArea
  id: scrollarea_hide_if
  hide_if:
    conditions:
      - left: {type: store, scope: page, path: /components_test/visibility/scrollarea_hide, default: false}
        op: "=="
        right: true
  children: []

- kind: ScrollArea
  id: scrollarea_required_permissions
  required_permissions: [components.layout.view]
  children: []</code></pre></div>
  </div>
</div>

## Notes

- `ScrollArea` needs bounded height from its parent; otherwise the page grows instead of scrolling internally.
- Use `stretch: true` when the scroll area must fill a `Column`, `ContentArea`, `Sidebar`, or `Splitter` pane.
- Use `scroll_x: false` for vertical-only panes to avoid horizontal scrollbars.
- Use `transparent: true` when the parent should provide the visible background.
