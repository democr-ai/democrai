# TextArea

[<- Back to Forms Components](./index.md)

`TextArea` is a multi-line text input. Use it for notes, descriptions, prompts, and longer free text.

## Contract

| Property | Type | Notes |
|---|---|---|
| `label` | `str` | Input label. |
| `value` | `str` | Current text value. Supports literal, store binding, and data-model binding. |
| `placeholder` | `str` | Placeholder shown while empty. |
| `auto_resize` | `bool` | Allows the client to grow the text area with content. |
| `disabled` | `bool` | Disables user editing. |
| `rows` | `int` | Initial visible row count. |
| `onChangeAction` | action object | Action dispatched while editing. Action objects can include `confirm`. |

Value collected by actions: `str`.

## Action Confirmation

`TextArea` supports confirmation on `onChangeAction`. If the user cancels the dialog, the change action is not sent to the backend.

The component test page exposes a text-area action counter and the last received payload so dispatch can be checked directly after confirming.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="textarea confirm example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="textarea-confirm-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="textarea-confirm-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="textarea-confirm-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>field = sdk.ui.TextArea(
    &quot;confirm_python_textarea&quot;,
    label=sdk.i18n.t(&quot;components.textarea.confirm.python_label&quot;),
    value=&quot;Python text area&quot;,
    placeholder=sdk.i18n.t(&quot;components.textarea.confirm.placeholder&quot;),
    rows=2,
)
field.set_prop(
    &quot;onChangeAction&quot;,
    {
        &quot;name&quot;: &quot;components.textarea_confirm_action&quot;,
        &quot;context&quot;: {&quot;source&quot;: &quot;python_change&quot;},
        &quot;confirm&quot;: {
            &quot;text&quot;: sdk.i18n.t(&quot;components.textarea.confirm.prompt&quot;),
            &quot;confirm_text&quot;: sdk.i18n.t(&quot;components.textarea.confirm.accept&quot;),
            &quot;cancel_text&quot;: sdk.i18n.t(&quot;components.textarea.confirm.cancel&quot;),
        },
    },
)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="textarea-confirm-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: TextArea
  id: confirm_yaml_textarea
  label: &quot;@t/components.textarea.confirm.yaml_label&quot;
  value: YAML text area
  placeholder: &quot;@t/components.textarea.confirm.placeholder&quot;
  rows: 2
  onChangeAction:
    name: components.textarea_confirm_action
    context:
      source: yaml_change
    confirm:
      text: &quot;@t/components.textarea.confirm.prompt&quot;
      confirm_text: &quot;@t/components.textarea.confirm.accept&quot;
      cancel_text: &quot;@t/components.textarea.confirm.cancel&quot;</code></pre></div>
  </div>
</div>

## Example

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="TextArea example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="textarea-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="textarea-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="textarea-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>field = sdk.ui.TextArea(
    "components_test_forms_textarea_store",
    label="TextArea",
    value=bound.store("/components_test/forms/textarea/store", scope="page", default="Initial notes"),
    placeholder="Write notes",
    rows=2,
)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="textarea-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: TextArea
  id: components_test_forms_yaml_textarea
  label: "TextArea YAML"
  value: {type: store, scope: page, path: /components_test/forms/textarea/store, default: "Initial notes"}
  placeholder: "Write notes"
  rows: 2</code></pre></div>
  </div>
</div>

## Runtime

Use `collect_input_ids` to read the current text. Use `value.set` property updates, `stateUpdate`, or `dataModelUpdate` to change the value from an action.
