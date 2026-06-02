# TagsInput

[<- Back to Forms Components](./index.md)

`TagsInput` edits a compact list of scalar values as removable chips. Use it for short list fields where the user adds one value at a time, such as MIME types, labels, simple numeric values, boolean flags, or values selected from a fixed option set.

## Contract

| Property | Type | Notes |
|---|---|---|
| `label` | `str` | Input label. |
| `value` | `list` | Current chip values. Supports literal, store binding, and data-model binding. |
| `placeholder` | `str` | Placeholder for text and number input modes. |
| `add_label` | `str` | Add button label. Defaults to `Add`. |
| `item_schema` | `dict` | Required. Describes the value inserted by the input control. |
| `action` / `params` | `str` or action object / `dict` | Optional action emitted when the list changes. |

Collected value: `list`.

## Item Schema

| `item_schema.type` | Input | Value shape |
|---|---|---|
| `text` | Text input | `str` |
| `string` | Text input | `str` |
| `number` | Number input | `int` or `float` |
| `boolean` | `true` / `false` select | `bool` |
| `select` | Select input | Option `value` |

`item_schema` is required. For `select`, `item_schema.options` is required and each option must define `label` and `value`.

## Example

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="TagsInput example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="tagsinput-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="tagsinput-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="tagsinput-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>field = sdk.ui.TagsInput(
    "components_test_tags_store",
    label="TagsInput store",
    value=bound.store(
        "/components_test/list_inputs/tags/store",
        scope="page",
        default=["image/png"],
    ),
    placeholder="image/webp",
    item_schema={"type": "text"},
)
field.set_show_if({
    "left": bound.store("/components_test/list_inputs/tags/show", scope="page", default=True),
    "op": "==",
    "right": True,
})
field.set_hide_if({
    "left": bound.store("/components_test/list_inputs/tags/hide", scope="page", default=False),
    "op": "==",
    "right": True,
})
field.set_required_permissions(["components.content.view"])</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="tagsinput-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: TagsInput
  id: components_test_tags_yaml_store
  label: TagsInput YAML store
  value: {type: store, scope: page, path: /components_test/list_inputs/tags/store, default: ["image/png"]}
  placeholder: image/webp
  item_schema:
    type: text
  show_if:
    left: {type: store, scope: page, path: /components_test/list_inputs/tags/show, default: true}
    op: "=="
    right: true
  hide_if:
    left: {type: store, scope: page, path: /components_test/list_inputs/tags/hide, default: false}
    op: "=="
    right: true
  required_permissions: [components.content.view]</code></pre></div>
  </div>
</div>

## Data Model Binding

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="TagsInput data model example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="tagsinput-data-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="tagsinput-data-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="tagsinput-data-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>sdk.ui.TagsInput(
    "components_test_tags_data",
    label="TagsInput data",
    value=bound.data("/components_test/list_inputs/tags/data", default=["image/jpeg"]),
    item_schema={
        "type": "select",
        "options": [
            {"label": "PNG", "value": "image/png"},
            {"label": "JPEG", "value": "image/jpeg"},
            {"label": "WebP", "value": "image/webp"},
        ],
    },
)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="tagsinput-data-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: TagsInput
  id: components_test_tags_yaml_data
  label: TagsInput YAML data
  value: "@data/components_test/list_inputs/tags/data"
  item_schema:
    type: select
    options:
      - label: PNG
        value: image/png
      - label: JPEG
        value: image/jpeg
      - label: WebP
        value: image/webp</code></pre></div>
  </div>
</div>

## Direct Property Update

Declare `value.set` before sending direct property updates to `value`.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="TagsInput property update example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="tagsinput-update-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="tagsinput-update-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="tagsinput-update-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>field = sdk.ui.TagsInput(
    "components_test_tags_live",
    label="TagsInput property update",
    value=["image/png"],
    item_schema={"type": "select", "options": mime_options},
)
field.allow("value.set")</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="tagsinput-update-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: TagsInput
  id: components_test_tags_yaml_live
  label: TagsInput YAML property update
  value: ["image/png"]
  capabilities: [value.set]
  item_schema:
    type: select
    options:
      - label: PNG
        value: image/png</code></pre></div>
  </div>
</div>

## Form Field

Inside `Form.model`, use `type: tags`. The field accepts the same `item_schema` contract as the standalone component.

```yaml
- name: mime_types
  label: MIME types
  type: tags
  value: ["image/png"]
  placeholder: image/jpeg
  item_schema:
    type: text
```
