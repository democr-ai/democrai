# EditableList

[<- Back to Forms Components](./index.md)

`EditableList` edits a list as visible rows. Use it when every item should stay directly editable instead of being compressed into chips.

The current contract supports lists of strings. Each row is either a text input or a select input, depending on `item_schema`.

## Contract

| Property | Type | Notes |
|---|---|---|
| `value` | `list[str]` | Current row values. Supports literal, store binding, and data-model binding. |
| `item_label` | `str` | Label shown above the list. |
| `add_label` | `str` | Add button label. Defaults to `Add`. |
| `remove_label` | `str` | Remove button label. Defaults to `Remove`. |
| `submit_label` | `str` | Save button label. Defaults to `Save`. |
| `placeholder` | `str` | Placeholder for text rows. |
| `item_schema` | `dict` | Required. Describes each row input. |
| `action` / `params` | `str` or action object / `dict` | Optional action emitted by the save button. |
| `track_loading` | `str` or `list[str]` | Action names used to show save loading state. |

Collected value: `list[str]`.

## Item Schema

| `item_schema.type` | Row input | Notes |
|---|---|---|
| `text` | Text input | Row value is the entered string. |
| `select` | Select input | `options` is required. Each option must define string `label` and string `value`. |

`item_schema` is required. There is no default row type.

## Example

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="EditableList example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="editablelist-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="editablelist-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="editablelist-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>field = sdk.ui.EditableList(
    "components_test_editable_list_store",
    item_label="EditableList store",
    value=bound.store(
        "/components_test/list_inputs/editable_list/store",
        scope="page",
        default=["chat"],
    ),
    add_label="Add capability",
    remove_label="Remove",
    submit_label="Save",
    item_schema={"type": "select", "options": capability_options},
)
field.set_show_if({
    "left": bound.store("/components_test/list_inputs/editable_list/show", scope="page", default=True),
    "op": "==",
    "right": True,
})
field.set_hide_if({
    "left": bound.store("/components_test/list_inputs/editable_list/hide", scope="page", default=False),
    "op": "==",
    "right": True,
})
field.set_required_permissions(["components.content.view"])</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="editablelist-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: EditableList
  id: components_test_editable_list_yaml_store
  item_label: EditableList YAML store
  value: {type: store, scope: page, path: /components_test/list_inputs/editable_list/store, default: ["chat"]}
  add_label: Add capability
  remove_label: Remove
  submit_label: Save
  item_schema:
    type: select
    options:
      - label: Chat
        value: chat
      - label: Reasoning
        value: reasoning
  show_if:
    left: {type: store, scope: page, path: /components_test/list_inputs/editable_list/show, default: true}
    op: "=="
    right: true
  hide_if:
    left: {type: store, scope: page, path: /components_test/list_inputs/editable_list/hide, default: false}
    op: "=="
    right: true
  required_permissions: [components.content.view]</code></pre></div>
  </div>
</div>

## Data Model Binding

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="EditableList data model example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="editablelist-data-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="editablelist-data-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="editablelist-data-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>sdk.ui.EditableList(
    "components_test_editable_list_data",
    item_label="EditableList data",
    value=bound.data("/components_test/list_inputs/editable_list/data", default=["reasoning"]),
    add_label="Add capability",
    remove_label="Remove",
    submit_label="Save",
    item_schema={"type": "select", "options": capability_options},
)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="editablelist-data-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: EditableList
  id: components_test_editable_list_yaml_data
  item_label: EditableList YAML data
  value: "@data/components_test/list_inputs/editable_list/data"
  add_label: Add capability
  remove_label: Remove
  submit_label: Save
  item_schema:
    type: select
    options:
      - label: Chat
        value: chat
      - label: Reasoning
        value: reasoning</code></pre></div>
  </div>
</div>

## Direct Property Update

Declare `value.set` before sending direct property updates to `value`.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="EditableList property update example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="editablelist-update-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="editablelist-update-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="editablelist-update-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>field = sdk.ui.EditableList(
    "components_test_editable_list_live",
    item_label="EditableList property update",
    value=["chat"],
    add_label="Add capability",
    remove_label="Remove",
    submit_label="Save",
    item_schema={"type": "select", "options": capability_options},
)
field.allow("value.set")</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="editablelist-update-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: EditableList
  id: components_test_editable_list_yaml_live
  item_label: EditableList YAML property update
  value: ["chat"]
  capabilities: [value.set]
  add_label: Add capability
  remove_label: Remove
  submit_label: Save
  item_schema:
    type: select
    options:
      - label: Chat
        value: chat</code></pre></div>
  </div>
</div>

## Form Field

Inside `Form.model`, use `type: editable_list`. The field accepts the same `item_schema` contract as the standalone component.

```yaml
- name: capabilities
  label: Capabilities
  type: editable_list
  value: ["chat"]
  add_label: Add capability
  remove_label: Remove
  submit_label: Save
  item_schema:
    type: select
    options:
      - label: Chat
        value: chat
```
