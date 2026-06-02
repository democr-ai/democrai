# ContentArea

[<- Back to Layout Components](./index.md)

## Definition

`ContentArea` marks the main content region of a structured layout. It is a container for page content beside or below shell elements such as `Sidebar`, `Header`, or split panes.

## Scope

Use `ContentArea` for the primary workspace of a page. It is a general container, not a layout-direction primitive. The first child should normally be a layout component with explicit child distribution semantics, such as `Column`, `Row`, `ScrollArea`, or `Splitter`.

Use `Column` for vertical stacking inside the workspace, `Row` for horizontal distribution, and `ScrollArea` when content can overflow. This keeps the behavior predictable across desktop and web clients.

## Properties

| Property | Type | Default | Notes |
|---|---|---|---|
| `children` | `list[str | Component]` | `[]` | Content rendered in the main area. Prefer a single explicit layout container as the first child. |
| `stretch` | `bool` | `false` | Lets the content area fill available space. |
| `style` | `string` | `None` | Common component style property. Supports direct property updates. |

## Static ContentArea

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="ContentArea static example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="contentarea-static-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="contentarea-static-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="contentarea-static-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>body = sdk.ui.Column("content_body", ["main_text"])
builder.add(body)

content = sdk.ui.ContentArea("content_area", [body.id])
content.set_property("stretch", True)
builder.add(content)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="contentarea-static-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: ContentArea
  id: content_area
  stretch: true
  children:
    - kind: Column
      id: content_body
      children:
        - main_text</code></pre></div>
  </div>
</div>

## First-Level Layout

`ContentArea` should not be used as the component that decides whether repeated children flow vertically or horizontally. Put a layout container at the first level and update that container when content changes dynamically.

```python
body = sdk.ui.Column("content_body", ["row_1", "row_2"])
body.set_property("stretch", True)
builder.add(body)

content = sdk.ui.ContentArea("content_area", [body.id])
content.set_property("stretch", True)
builder.add(content)
```

## With ScrollArea

Use this pattern when the main content can be taller than the available space.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="ContentArea with ScrollArea example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="contentarea-scroll-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="contentarea-scroll-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="contentarea-scroll-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>stack = sdk.ui.Column("content_stack", ["row_1", "row_2"])
builder.add(stack)

scroll = sdk.ui.ScrollArea("content_scroll", [stack.id])
scroll.set_property("stretch", True)
scroll.set_property("scroll_x", False)
builder.add(scroll)

content = sdk.ui.ContentArea("content_area", [scroll.id])
content.set_property("stretch", True)
builder.add(content)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="contentarea-scroll-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: ContentArea
  id: content_area
  stretch: true
  children:
    - kind: ScrollArea
      id: content_scroll
      stretch: true
      scroll_x: false
      children:
        - kind: Column
          id: content_stack
          children:
            - row_1
            - row_2</code></pre></div>
  </div>
</div>

## Store Binding

Bind `style` when the content area state is driven by the page store.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="ContentArea store binding example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="contentarea-store-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="contentarea-store-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="contentarea-store-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>content = sdk.ui.ContentArea("content_area_store", [body.id])
content.set_property("stretch", True)
content.set_property(
    "style",
    bound.store("/components_test/contentarea/style", scope="page", default=""),
)
builder.add(content)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="contentarea-store-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: ContentArea
  id: content_area_store
  stretch: true
  style: {type: store, scope: page, path: /components_test/contentarea/style, default: ""}
  children:
    - content_body</code></pre></div>
  </div>
</div>

## Data Model Binding

Use data-model binding when the content area style comes from the surface data model.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="ContentArea data model binding example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="contentarea-data-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="contentarea-data-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="contentarea-data-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>content = sdk.ui.ContentArea("content_area_data", [body.id])
content.set_property("stretch", True)
content.set_property(
    "style",
    bound.data("/components_test/contentarea_model/style", default=""),
)
builder.add(content)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="contentarea-data-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: ContentArea
  id: content_area_data
  stretch: true
  style: "@data/components_test/contentarea_model/style"
  children:
    - content_body</code></pre></div>
  </div>
</div>

## Property Updates

Declare capabilities before updating `style` directly.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="ContentArea property update example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="contentarea-update-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="contentarea-update-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="contentarea-update-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>content = sdk.ui.ContentArea("content_area_live", [body.id])
content.set_property("stretch", True)
content.allow("style.set")
builder.add(content)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="contentarea-update-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: ContentArea
  id: content_area_live
  stretch: true
  capabilities: [style.set]
  children:
    - content_body</code></pre></div>
  </div>
</div>

The action can update store, data model, and live content-area properties:

```python
return sdk.effects.respond(
    sdk.effects.ui_property_update("content_area_live", "style", next_style, surface_id=surface_id),
)
```

## Dynamic Children

When the main workspace changes without replacing the whole page, update the first-level layout container inside `ContentArea`. Do not append repeated rows directly to `ContentArea.children` unless the client-specific layout behavior is acceptable for that use case.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="ContentArea dynamic children example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="contentarea-dynamic-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="contentarea-dynamic-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="contentarea-dynamic-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>body = sdk.ui.Column("content_area_dynamic_body", ["row_1", "row_2"])
body.set_property("stretch", True)
body.allow("children.append", "children.remove")
builder.add(body)

content = sdk.ui.ContentArea("content_area_dynamic", [body.id])
content.set_property("stretch", True)
builder.add(content)

# In the action:
return sdk.effects.respond(
    sdk.effects.ui_collection_append("content_area_dynamic_body", "children", row_component_dict, surface_id=surface_id),
)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="contentarea-dynamic-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: ContentArea
  id: content_area_dynamic
  stretch: true
  children:
    - kind: Column
      id: content_area_dynamic_body
      stretch: true
      capabilities: [children.append, children.remove]
      children:
        - kind: Text
          id: content_area_dynamic_row_1
          text: "Dynamic row 1"
        - kind: Text
          id: content_area_dynamic_row_2
          text: "Dynamic row 2"</code></pre></div>
  </div>
</div>

## Visibility And Permissions

`show_if`, `hide_if`, and `required_permissions` are available on `ContentArea`.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="ContentArea visibility example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="contentarea-visibility-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="contentarea-visibility-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="contentarea-visibility-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>content.set_show_if({
    "conditions": [
        {"left": bound.store("/components_test/visibility/contentarea_show", scope="page", default=True), "op": "==", "right": True}
    ]
})

content.set_hide_if({
    "conditions": [
        {"left": bound.store("/components_test/visibility/contentarea_hide", scope="page", default=False), "op": "==", "right": True}
    ]
})

content.set_required_permissions(["components.layout.view"])</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="contentarea-visibility-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: ContentArea
  id: content_area_show_if
  show_if:
    conditions:
      - left: {type: store, scope: page, path: /components_test/visibility/contentarea_show, default: true}
        op: "=="
        right: true
  children:
    - content_body

- kind: ContentArea
  id: content_area_hide_if
  hide_if:
    conditions:
      - left: {type: store, scope: page, path: /components_test/visibility/contentarea_hide, default: false}
        op: "=="
        right: true
  children:
    - content_body

- kind: ContentArea
  id: content_area_required_permissions
  required_permissions: [components.layout.view]
  children:
    - content_body</code></pre></div>
  </div>
</div>

## Notes

- `ContentArea` identifies the main workspace; it is not a layout-direction or scrolling primitive.
- Put a direction-aware layout container as the first child when repeated content must flow predictably.
- Put `ScrollArea` inside `ContentArea` for long content.
- Use `stretch: true` when `ContentArea` must fill the remaining width or height in a shell layout.
- Keep inner wrappers at `min-height: 0` when combining `ContentArea` with bounded-height layouts and scroll areas.
