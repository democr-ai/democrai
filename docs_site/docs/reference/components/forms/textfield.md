# TextField

[<- Back to Forms Components](./index.md)

`TextField` is a single-line text input. Use it for string values such as names, titles, search terms, and short identifiers.

## Contract

| Property | Type | Notes |
|---|---|---|
| `label` | `str` | Input label. |
| `value` | `str` | Current text value. Supports literal, store binding, and data-model binding. |
| `placeholder` | `str` | Placeholder shown while empty. |
| `password` | `bool` | Renders the field as a password input. |
| `action` | `str` or action object | Action dispatched when the user presses Enter. Action objects can include `confirm`. |
| `onChangeAction` | action object | Action dispatched while typing when `onChangeMode` is a remote/live mode. Action objects can include `confirm`. |
| `onChangeMode` | `str` | Dispatch mode for `onChangeAction`. Remote/live modes include `live`, `autocomplete`, `search`, `search_suggest`, `remote_validate`, and `remote_preview`. |

Value collected by actions: `str`.

## Action Confirmation

`TextField` supports confirmation for both the Enter action and remote/live change action. If the user cancels the dialog, the action is not sent to the backend.

The component test page exposes a text-field action counter and the last received payload so dispatch can be checked directly after confirming.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="textfield confirm example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="textfield-confirm-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="textfield-confirm-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="textfield-confirm-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>field = sdk.ui.TextField(
    &quot;confirm_python_textfield&quot;,
    label=sdk.i18n.t(&quot;components.textfield.confirm.python_label&quot;),
    value=&quot;Python text&quot;,
    placeholder=sdk.i18n.t(&quot;components.textfield.confirm.placeholder&quot;),
)
field.set_prop(
    &quot;action&quot;,
    {
        &quot;name&quot;: &quot;components.textfield_confirm_action&quot;,
        &quot;context&quot;: {&quot;source&quot;: &quot;python_enter&quot;},
        &quot;confirm&quot;: {
            &quot;text&quot;: sdk.i18n.t(&quot;components.textfield.confirm.prompt&quot;),
            &quot;confirm_text&quot;: sdk.i18n.t(&quot;components.textfield.confirm.accept&quot;),
            &quot;cancel_text&quot;: sdk.i18n.t(&quot;components.textfield.confirm.cancel&quot;),
        },
    },
)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="textfield-confirm-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: TextField
  id: confirm_yaml_textfield
  label: &quot;@t/components.textfield.confirm.yaml_label&quot;
  value: YAML text
  placeholder: &quot;@t/components.textfield.confirm.placeholder&quot;
  onChangeMode: live
  onChangeAction:
    name: components.textfield_confirm_action
    context:
      source: yaml_change
    confirm:
      text: &quot;@t/components.textfield.confirm.change_prompt&quot;
      confirm_text: &quot;@t/components.textfield.confirm.accept&quot;
      cancel_text: &quot;@t/components.textfield.confirm.cancel&quot;</code></pre></div>
  </div>
</div>

## Example

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="TextField example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="textfield-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="textfield-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="textfield-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>field = sdk.ui.TextField(
    "components_test_forms_textfield_store",
    label="TextField",
    value=bound.store("/components_test/forms/textfield/store", scope="page", default="Draft title"),
    placeholder="Write text",
)
field.set_show_if({
    "conditions": [
        {"left": bound.store("/components_test/forms/visibility/textfield_show", scope="page", default=True), "op": "==", "right": True}
    ]
})
field.set_hide_if({
    "conditions": [
        {"left": bound.store("/components_test/forms/visibility/textfield_hide", scope="page", default=False), "op": "==", "right": True}
    ]
})
field.set_required_permissions(["components.content.view"])</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="textfield-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: TextField
  id: components_test_forms_yaml_textfield
  label: "TextField YAML"
  value: {type: store, scope: page, path: /components_test/forms/textfield/store, default: "Draft title"}
  placeholder: "Write text"
  required_permissions: [components.content.view]</code></pre></div>
  </div>
</div>

## Reading Values

Use a button or submit action with `collect_input_ids` to read the current value.

```python
button = sdk.ui.Button(
    "read_textfield",
    "Read",
    action="components.forms_test_read",
    params={"key": "textfield", "field_ids": ["components_test_forms_textfield_store"]},
)
button.set_property("collect_input_ids", ["components_test_forms_textfield_store"])
```

`value=bound.store(...)` or `value=bound.data(...)` reads from that source. User edits do not write back automatically; use an action that emits `stateUpdate`, `dataModelUpdate`, or a direct property update.
