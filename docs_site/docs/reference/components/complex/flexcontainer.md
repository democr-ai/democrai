# FlexContainer

[<- Back to Complex Components](./index.md)

## Purpose

`FlexContainer` is a direction-agnostic fill container. It tells each client to let the container grow into the available space without adding row or column semantics of its own.

Use it when child content must remain responsive to the space around it:

- with no children, it acts as a spacer between siblings
- with children, it acts as a growing wrapper for a child layout or data component
- inside a page shell, it fills the remaining body or sidebar space

`FlexContainer` does not define direction, wrapping, alignment, or spacing. Put `Row`, `Column`, `List`, `Grid`, or another layout component inside it when the children need those rules.

## Constructor

```python
FlexContainer(
    id: str,
    children: list[str | Component] | None = None,
)
```

## Properties

| Property | Type | Default | Description |
|---|---:|---:|---|
| `children` | `list[str | Component]` | `[]` | Child components rendered inside the fill area. Empty children make the container behave as a spacer. |
| `style` | `str | dict` | none | Common style property. Useful for preview frames, padding, and borders. |
| `visible` | `bool` | `true` | Common runtime visibility property. |

## Store-Bound Card Children

The demo uses `FlexContainer` as the fill wrapper and renders six `Card` components as first-level children. Each card keeps a fixed width and reads its title, body, and badge from page store.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="FlexContainer card children">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="flex-card-children-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="flex-card-children-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="flex-card-children-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>for index, (title, text, badge) in enumerate(card_values):
    builder.set_store(f"/components_test/flex/cards/{index}/title", title, scope="page")
    builder.set_store(f"/components_test/flex/cards/{index}/text", text, scope="page")
    builder.set_store(f"/components_test/flex/cards/{index}/badge", badge, scope="page")

card = sdk.ui.Card(
    "flex_card_0",
    [
        sdk.ui.Title(
            "flex_card_0_title",
            bound.store("/components_test/flex/cards/0/title", scope="page", default="Intake"),
            level=3,
        ),
        sdk.ui.Text(
            "flex_card_0_text",
            bound.store("/components_test/flex/cards/0/text", scope="page", default="Direct child card fed by page store."),
        ),
        sdk.ui.Badge(
            "flex_card_0_badge",
            bound.store("/components_test/flex/cards/0/badge", scope="page", default="Store"),
            variant="info",
        ),
    ],
    variant="default",
)
card.set_property("style", "width: 240px; min-width: 240px;")

wrapper = sdk.ui.FlexContainer("card_wrapper", ["flex_card_0", "flex_card_1", "flex_card_2", "flex_card_3", "flex_card_4", "flex_card_5"])
wrapper.allow("style.set", "children.append", "children.set")</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="flex-card-children-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: FlexContainer
  id: card_wrapper
  capabilities: [style.set, children.append, children.set]
  children:
    - kind: Card
      id: flex_card_0
      variant: default
      style: "width: 240px; min-width: 240px;"
      children:
        - kind: Title
          id: flex_card_0_title
          text: {type: store, scope: page, path: /components_test/flex/cards/0/title, default: Intake}
          level: 3
        - kind: Text
          id: flex_card_0_text
          text: {type: store, scope: page, path: /components_test/flex/cards/0/text, default: "Direct child card fed by page store."}
        - kind: Badge
          id: flex_card_0_badge
          text: {type: store, scope: page, path: /components_test/flex/cards/0/badge, default: Store}
          variant: info
    # The demo repeats the same Card structure for cards 1-5.</code></pre></div>
  </div>
</div>

## Spacer Example

An empty `FlexContainer` grows between siblings. In a `Row`, this pushes the following item to the opposite side.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="FlexContainer spacer">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="flex-spacer-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="flex-spacer-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="flex-spacer-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>spacer = sdk.ui.FlexContainer("toolbar_spacer")
row = sdk.ui.Row("toolbar", ["left_action", spacer.id, "right_action"])</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="flex-spacer-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Row
  id: toolbar
  children:
    - left_action
    - kind: FlexContainer
      id: toolbar_spacer
    - right_action</code></pre></div>
  </div>
</div>

## Bindings and Updates

`children` is the main structural surface. Use direct child components when the container should only provide a fill area; use a child `List`, `Grid`, `Row`, or `Column` when the child layout needs its own rendering rules. Common properties such as `style`, `visible`, `show_if`, `hide_if`, and `required_permissions` work like other components.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="FlexContainer bindings">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="flex-bind-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="flex-bind-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="flex-bind-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>store_wrapper = sdk.ui.FlexContainer("store_wrapper", ["flex_card_0", "flex_card_1"])
store_wrapper.set_property(
    "style",
    bound.store("/components_test/flex/panel_style", scope="page", default="padding: 12px;"),
)

data_wrapper = sdk.ui.FlexContainer("data_wrapper", ["data_text"])
data_wrapper.set_property(
    "style",
    bound.data("/components_test/flex_model/panel_style", default="padding: 12px;"),
)

live_wrapper = sdk.ui.FlexContainer("live_wrapper", ["live_text"])
live_wrapper.allow("children.append")</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="flex-bind-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: FlexContainer
  id: store_wrapper
  style: {type: store, scope: page, path: /components_test/flex/panel_style, default: "padding: 12px;"}
  children: [flex_card_0, flex_card_1]

- kind: FlexContainer
  id: data_wrapper
  style: "@data/components_test/flex_model/panel_style"
  children: [data_text]

- kind: FlexContainer
  id: live_wrapper
  capabilities: [children.append]
  children: [live_text]</code></pre></div>
  </div>
</div>

Runtime updates:

```python
surface_id = ctx["_surface_id"]

sdk.effects.ui_messages([
    {
        "stateUpdate": {
            "scope": "page",
            "values": {
                "/components_test/flex/cards/0/title": "Plan",
                "/components_test/flex/cards/0/text": "Updated through page store.",
                "/components_test/flex/cards/0/badge": "Updated",
                "/components_test/flex/panel_style": "padding: 12px; border: 1px solid #4f7cff;",
            },
        }
    }
])

sdk.ui.Builder.build_data_model_update_payload(
    surface_id=surface_id,
    data={"components_test": {"flex_model": {"panel_style": "padding: 12px;"}}},
)

sdk.effects.ui_collection_append(
    "live_wrapper",
    "children",
    sdk.ui.Text("new_child", "Added child").to_dict(),
    surface_id=surface_id,
)
```

## Visibility and Permissions

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="FlexContainer visibility">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="flex-vis-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="flex-vis-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="flex-vis-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>wrapper.set_show_if({
    "conditions": [
        {
            "left": bound.store("/components_test/flex/show", scope="page", default=True),
            "op": "==",
            "right": True,
        }
    ]
})
wrapper.set_hide_if({
    "conditions": [
        {
            "left": bound.store("/components_test/flex/hide", scope="page", default=False),
            "op": "==",
            "right": True,
        }
    ]
})
wrapper.set_required_permissions(["components.layout.view"])</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="flex-vis-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: FlexContainer
  id: guarded_wrapper
  required_permissions: [components.layout.view]
  show_if:
    conditions:
      - left: {type: store, scope: page, path: /components_test/flex/show, default: true}
        op: "=="
        right: true
  hide_if:
    conditions:
      - left: {type: store, scope: page, path: /components_test/flex/hide, default: false}
        op: "=="
        right: true</code></pre></div>
  </div>
</div>
