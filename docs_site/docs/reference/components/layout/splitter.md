# Splitter

[<- Back to Layout Components](./index.md)

`Splitter` creates a horizontal resizable pane group. Use it when adjacent areas must share bounded space and the user needs to resize them, for example list/detail, editor/preview, or comparison views.

The component is a container: each pane is a child component. Put scroll containers inside the panes when pane content must scroll independently.

## Properties

| Property | Type | Default | Notes |
|---|---|---|---|
| `children` | `list[str | Component]` | `[]` | Pane components. The desktop and web renderers support runtime append/remove. |
| `sizes` | `list[int]` | equal split | Initial pane sizes. Web normalizes values to percentages; desktop passes values to `QSplitter.setSizes`. |
| `max_sizes` | `list[int]` | `[]` | Optional maximum width per pane. Use `0` or omit an entry for no maximum. |
| `stretch` | `bool` | `false` | Allows the splitter to fill available flex space. |

## Static Splitter

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="Splitter static example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="splitter-static-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="splitter-static-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="splitter-static-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>left = sdk.ui.Column("splitter_left", [])
left.set_property("align", "fill")
left.set_property("stretch", True)
left.set_property("style", "min-height: 0;")
builder.add(left)

right = sdk.ui.Column("splitter_right", [])
right.set_property("align", "fill")
right.set_property("stretch", True)
right.set_property("style", "min-height: 0;")
builder.add(right)

splitter = sdk.ui.Splitter("splitter", [left.id, right.id])
splitter.set_property("stretch", True)
splitter.set_property("sizes", [650, 350])
builder.add(splitter)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="splitter-static-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Splitter
  id: splitter
  stretch: true
  sizes: [650, 350]
  children:
    - kind: Column
      id: splitter_left
      align: fill
      stretch: true
      style: "min-height: 0;"
      children: []
    - kind: Column
      id: splitter_right
      align: fill
      stretch: true
      style: "min-height: 0;"
      children: []</code></pre></div>
  </div>
</div>

## Store Binding

Bind `sizes` and `max_sizes` to page store values when pane sizing is part of client state.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="Splitter store binding example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="splitter-store-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="splitter-store-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="splitter-store-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>splitter = sdk.ui.Splitter("splitter_store", [left.id, right.id])
splitter.set_property("stretch", True)
splitter.set_property(
    "sizes",
    bound.store("/components_test/splitter/sizes", scope="page", default=[500, 300]),
)
splitter.set_property(
    "max_sizes",
    bound.store("/components_test/splitter/max_sizes", scope="page", default=[0, 0]),
)
builder.add(splitter)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="splitter-store-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Splitter
  id: splitter_store
  stretch: true
  sizes: {type: store, scope: page, path: /components_test/splitter/sizes, default: [500, 300]}
  max_sizes: {type: store, scope: page, path: /components_test/splitter/max_sizes, default: [0, 0]}
  children:
    - splitter_left
    - splitter_right</code></pre></div>
  </div>
</div>

## Data Model Binding

Use data-model binding when pane sizing comes from the surface data model.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="Splitter data model binding example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="splitter-data-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="splitter-data-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="splitter-data-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>splitter = sdk.ui.Splitter("splitter_data", [left.id, right.id])
splitter.set_property("stretch", True)
splitter.set_property(
    "sizes",
    bound.data("/components_test/splitter_model/sizes", default=[500, 300]),
)
splitter.set_property(
    "max_sizes",
    bound.data("/components_test/splitter_model/max_sizes", default=[0, 0]),
)
builder.add(splitter)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="splitter-data-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Splitter
  id: splitter_data
  stretch: true
  sizes: "@data/components_test/splitter_model/sizes"
  max_sizes: "@data/components_test/splitter_model/max_sizes"
  children:
    - splitter_left
    - splitter_right</code></pre></div>
  </div>
</div>

## Property Updates

Declare capabilities before updating `sizes` or `max_sizes` directly.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="Splitter property update example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="splitter-update-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="splitter-update-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="splitter-update-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>splitter = sdk.ui.Splitter("splitter_live", [left.id, right.id])
splitter.set_property("stretch", True)
splitter.set_property("sizes", [500, 300])
splitter.set_property("max_sizes", [0, 0])
splitter.allow("sizes.set", "max_sizes.set")
builder.add(splitter)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="splitter-update-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Splitter
  id: splitter_live
  stretch: true
  sizes: [500, 300]
  max_sizes: [0, 0]
  capabilities: [sizes.set, max_sizes.set]
  children:
    - splitter_left
    - splitter_right</code></pre></div>
  </div>
</div>

The action updates store, data model, and live splitter properties:

```python
return sdk.effects.respond(
    sdk.effects.ui_property_update("splitter_live", "sizes", [300, 500], surface_id=surface_id),
    sdk.effects.ui_property_update("splitter_live", "max_sizes", [0, 620], surface_id=surface_id),
)
```

## Dynamic Children

`children` supports append and remove updates. Update `sizes` in the same action so each pane has a non-zero size after the collection change.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="Splitter dynamic children example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="splitter-dynamic-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="splitter-dynamic-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="splitter-dynamic-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>splitter = sdk.ui.Splitter("splitter_dynamic", [pane_1.id, pane_2.id])
splitter.set_property("stretch", True)
splitter.set_property("sizes", [500, 300])
splitter.allow("children.append", "children.remove", "sizes.set")
builder.add(splitter)

# In the action:
return sdk.effects.respond(
    sdk.effects.ui_collection_append("splitter_dynamic", "children", pane_component_dict, surface_id=surface_id),
    sdk.effects.ui_property_update("splitter_dynamic", "sizes", [500, 300, 250], surface_id=surface_id),
)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="splitter-dynamic-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Splitter
  id: splitter_dynamic
  stretch: true
  sizes: [500, 300]
  capabilities: [children.append, children.remove, sizes.set]
  children:
    - kind: Column
      id: splitter_dynamic_pane_1
      align: fill
      stretch: true
      style: "min-height: 0;"
      children: []
    - kind: Column
      id: splitter_dynamic_pane_2
      align: fill
      stretch: true
      style: "min-height: 0;"
      children: []</code></pre></div>
  </div>
</div>

## Visibility And Permissions

`show_if`, `hide_if`, and `required_permissions` are available on `Splitter`.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="Splitter visibility example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="splitter-visibility-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="splitter-visibility-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="splitter-visibility-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>splitter.set_show_if({
    "conditions": [
        {"left": bound.store("/components_test/visibility/splitter_show", scope="page", default=True), "op": "==", "right": True}
    ]
})

splitter.set_hide_if({
    "conditions": [
        {"left": bound.store("/components_test/visibility/splitter_hide", scope="page", default=False), "op": "==", "right": True}
    ]
})

splitter.set_required_permissions(["components.layout.view"])</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="splitter-visibility-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Splitter
  id: splitter_show_if
  show_if:
    conditions:
      - left: {type: store, scope: page, path: /components_test/visibility/splitter_show, default: true}
        op: "=="
        right: true
  children: []

- kind: Splitter
  id: splitter_hide_if
  hide_if:
    conditions:
      - left: {type: store, scope: page, path: /components_test/visibility/splitter_hide, default: false}
        op: "=="
        right: true
  children: []

- kind: Splitter
  id: splitter_required_permissions
  required_permissions: [components.layout.view]
  children: []</code></pre></div>
  </div>
</div>

## Notes

- `Splitter` is horizontal in the current desktop and web renderers.
- Keep split panes at `min-height: 0` when the splitter lives inside a bounded-height layout.
- Use scroll areas inside panes for independent scrolling.
- Keep `sizes` aligned with the number of children when changing panes dynamically.
