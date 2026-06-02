# DropdownMenu

[<- Back to Effects](./index.md)

`DropdownMenu` renders a compact trigger button that opens a menu of contextual actions. Each item dispatches its own action and passes the item `context` object as the action payload.

## Python Contract

```python
sdk.ui.DropdownMenu(
    id: str,
    label: str,
    items: list[dict] | None = None,
    variant: str = "default",
)
```

## Supported Properties

| Property | Type | Required | Python | YAML | Notes |
|---|---|---|---|---|---|
| `id` | `str` | yes | constructor | `id` | Stable component id. |
| `label` | `str | binding` | yes | constructor / `set_property("label", ...)` | `label` | Trigger text. |
| `items` | `list[dict] | binding` | no | constructor / `set_property("items", ...)` | `items` | Menu entries. |
| `variant` | `str` | no | constructor | `variant` | Serialized trigger variant; current clients render the standard dropdown trigger. |
| `show_if` | rule | no | yes | yes | Generic visibility rule. |
| `hide_if` | rule | no | yes | yes | Generic visibility rule. |
| `required_permissions` | `list[str]` | no | yes | yes | Generic permission gate. |
| `enabled` | `bool` | no | `enabled.set` | `enabled.set` | Generic direct property update. |
| `visible` | `bool` | no | `visible.set` | `visible.set` | Generic direct property update. |

## Item Format

`items` is a list of objects. Each item uses this shape:

```python
{
    "label": "Archive",
    "action": {
        "name": "components.test_dropdown_select",
        "context": {"source": "static", "operation": "archive"},
    },
}
```

When the user clicks the item, the client dispatches `action.name` and sends `action.context` as the action context. Use explicit context keys for the values the action needs; the menu does not infer row or form data by itself.

## Action Confirmation

Menu item actions can include `confirm`. If the user cancels the dialog, no backend action is sent.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="DropdownMenu confirm example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="dropdown-confirm-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="dropdown-confirm-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="dropdown-confirm-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>menu = sdk.ui.DropdownMenu(
    &quot;confirm_python_dropdown&quot;,
    sdk.i18n.t(&quot;components.dropdown.confirm.python_label&quot;),
    [
        {
            &quot;label&quot;: sdk.i18n.t(&quot;components.dropdown.confirm.item_open&quot;),
            &quot;action&quot;: {
                &quot;name&quot;: &quot;components.dropdown_confirm_action&quot;,
                &quot;context&quot;: {&quot;source&quot;: &quot;python_dropdown&quot;, &quot;operation&quot;: &quot;open&quot;},
                &quot;confirm&quot;: {
                    &quot;text&quot;: sdk.i18n.t(&quot;components.dropdown.confirm.prompt&quot;),
                    &quot;confirm_text&quot;: sdk.i18n.t(&quot;components.dropdown.confirm.accept&quot;),
                    &quot;cancel_text&quot;: sdk.i18n.t(&quot;components.dropdown.confirm.cancel&quot;),
                },
            },
        }
    ],
)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="dropdown-confirm-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: DropdownMenu
  id: confirm_yaml_dropdown
  label: &quot;@t/components.dropdown.confirm.yaml_label&quot;
  items:
    - label: &quot;@t/components.dropdown.confirm.item_open&quot;
      action:
        name: components.dropdown_confirm_action
        context:
          source: yaml_dropdown
          operation: open
        confirm:
          text: &quot;@t/components.dropdown.confirm.prompt&quot;
          confirm_text: &quot;@t/components.dropdown.confirm.accept&quot;
          cancel_text: &quot;@t/components.dropdown.confirm.cancel&quot;</code></pre></div>
  </div>
</div>

## Static Menu

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="DropdownMenu static example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="dropdown-static-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="dropdown-static-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="dropdown-static-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>builder.add(
    sdk.ui.DropdownMenu(
        "actions_menu",
        "Static actions",
        [
            {
                "label": "Open",
                "action": {
                    "name": "components.test_dropdown_select",
                    "context": {"source": "static", "operation": "open"},
                },
            },
            {
                "label": "Archive",
                "action": {
                    "name": "components.test_dropdown_select",
                    "context": {"source": "static", "operation": "archive"},
                },
            },
        ],
    )
)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="dropdown-static-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: DropdownMenu
  id: actions_menu
  label: YAML static actions
  items:
    - label: YAML open
      action:
        name: components.test_dropdown_select
        context: {source: yaml_static, operation: open}
    - label: YAML archive
      action:
        name: components.test_dropdown_select
        context: {source: yaml_static, operation: archive}</code></pre></div>
  </div>
</div>

## Store Binding

Bind `label` and `items` to page store when the menu contents must change from an action.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="DropdownMenu store binding example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="dropdown-store-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="dropdown-store-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="dropdown-store-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>from democrai.sdk.ui import bound

menu = sdk.ui.DropdownMenu("store_menu", "Store actions")
menu.set_property(
    "label",
    bound.store("/components_test/dropdown/store_label", scope="page", default="Store actions"),
)
menu.set_property(
    "items",
    bound.store("/components_test/dropdown/store_items", scope="page", default=[]),
)
builder.add(menu)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="dropdown-store-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: DropdownMenu
  id: store_menu
  label: {type: store, scope: page, path: /components_test/dropdown/store_label, default: "Store actions"}
  items:
    type: store
    scope: page
    path: /components_test/dropdown/store_items
    default: []</code></pre></div>
  </div>
</div>

An action can replace both values:

```python
return sdk.effects.respond(
    sdk.effects.ui_messages([
        {
            "stateUpdate": {
                "scope": "page",
                "values": {
                    "/components_test/dropdown/store_label": "Store actions updated",
                    "/components_test/dropdown/store_items": updated_items,
                },
            }
        }
    ])
)
```

## Data Model Binding

Bind to the surface data model when the menu should follow data scoped to the rendered surface.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="DropdownMenu data model binding example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="dropdown-data-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="dropdown-data-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="dropdown-data-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>from democrai.sdk.ui import bound

menu = sdk.ui.DropdownMenu("data_menu", "Data actions")
menu.set_property(
    "label",
    bound.data("/components_test/dropdown_model/label", default="Data actions"),
)
menu.set_property(
    "items",
    bound.data("/components_test/dropdown_model/items", default=[]),
)
builder.add(menu)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="dropdown-data-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: DropdownMenu
  id: data_menu
  label: "@data/components_test/dropdown_model/label"
  items: "@data/components_test/dropdown_model/items"</code></pre></div>
  </div>
</div>

Target the current surface when updating the data model:

```python
surface_id = str(ctx.get("_surface_id") or "main").strip() or "main"
return sdk.effects.respond(
    sdk.effects.ui_messages([
        sdk.ui.Builder.build_data_model_update_payload(
            surface_id=surface_id,
            data={
                "components_test": {
                    "dropdown_model": {
                        "label": "Data actions updated",
                        "items": updated_items,
                    }
                }
            },
        )
    ])
)
```

## Direct Property Update

Direct updates are used for generic component properties such as `enabled` and `visible`. Declare the capability on the menu before an action targets it.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="DropdownMenu direct update example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="dropdown-direct-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="dropdown-direct-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="dropdown-direct-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>builder.add(
    sdk.ui.DropdownMenu("direct_menu", "Direct update actions", items)
    .allow("enabled.set", "visible.set")
)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="dropdown-direct-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: DropdownMenu
  id: direct_menu
  label: YAML direct actions
  capabilities: [enabled.set, visible.set]
  items:
    - label: YAML direct open
      action:
        name: components.test_dropdown_select
        context: {source: yaml_direct, operation: open}</code></pre></div>
  </div>
</div>

The action sends a `propertyUpdate` to the current surface:

```python
surface_id = str(ctx.get("_surface_id") or "main").strip() or "main"
target_id = str(ctx.get("target_id") or "direct_menu")
return sdk.effects.respond(
    sdk.effects.ui_messages([
        sdk.ui.Builder.build_property_update_payload(
            target_id,
            "enabled",
            False,
            surface_id=surface_id,
        )
    ])
)
```

## Visibility And Permissions

`DropdownMenu` supports the generic `show_if`, `hide_if`, and `required_permissions` gates.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="DropdownMenu visibility example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="dropdown-visibility-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="dropdown-visibility-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="dropdown-visibility-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>show_menu = sdk.ui.DropdownMenu("show_menu", "show_if menu", items)
show_menu.set_show_if({
    "conditions": [{
        "left": bound.store("/components_test/dropdown/show_menu", scope="page", default=True),
        "op": "==",
        "right": True,
    }]
})

permission_menu = sdk.ui.DropdownMenu("permission_menu", "Permission-gated menu", items)
permission_menu.set_required_permissions(["components.dropdown.use"])</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="dropdown-visibility-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: DropdownMenu
  id: show_menu
  label: YAML show_if menu
  show_if:
    conditions:
      - left: {type: store, scope: page, path: /components_test/dropdown/show_menu, default: true}
        op: "=="
        right: true
  items: []
- kind: DropdownMenu
  id: permission_menu
  label: YAML permission-gated menu
  required_permissions: [components.dropdown.use]
  items: []</code></pre></div>
  </div>
</div>
