# Checkbox

[<- Back to Forms Components](./index.md)

`Checkbox` is a boolean form input. Use it for explicit yes/no choices or multi-option checklists.

## Contract

| Property | Type | Notes |
|---|---|---|
| `label` | `str` | Text shown next to the checkbox. |
| `checked` | `bool` | Current boolean state. Supports literal, store binding, and data-model binding. |
| `action` | `str` or action object | Optional action emitted on change. Action objects can include `confirm`. |
| `params` | `dict` | Optional action context. |

Value collected by actions: `bool`.

## Action Confirmation

Use an action object with `confirm` to require confirmation before the checkbox change action is dispatched. If the user cancels the dialog, no backend action is sent and the checkbox keeps its previous state.

The component test page exposes a checkbox action counter and the last received payload so dispatch can be checked directly after confirming.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="checkbox confirm example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="checkbox-confirm-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="checkbox-confirm-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="checkbox-confirm-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>field = sdk.ui.Checkbox(
    &quot;confirm_python_checkbox&quot;,
    sdk.i18n.t(&quot;components.checkbox.confirm.python_label&quot;),
    checked=False,
)
field.set_prop(
    &quot;action&quot;,
    {
        &quot;name&quot;: &quot;components.checkbox_confirm_action&quot;,
        &quot;context&quot;: {&quot;source&quot;: &quot;python_checkbox&quot;},
        &quot;confirm&quot;: {
            &quot;text&quot;: sdk.i18n.t(&quot;components.checkbox.confirm.prompt&quot;),
            &quot;confirm_text&quot;: sdk.i18n.t(&quot;components.checkbox.confirm.accept&quot;),
            &quot;cancel_text&quot;: sdk.i18n.t(&quot;components.checkbox.confirm.cancel&quot;),
        },
    },
)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="checkbox-confirm-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Checkbox
  id: confirm_yaml_checkbox
  label: &quot;@t/components.checkbox.confirm.yaml_label&quot;
  checked: false
  action:
    name: components.checkbox_confirm_action
    context:
      source: yaml_checkbox
    confirm:
      text: &quot;@t/components.checkbox.confirm.prompt&quot;
      confirm_text: &quot;@t/components.checkbox.confirm.accept&quot;
      cancel_text: &quot;@t/components.checkbox.confirm.cancel&quot;</code></pre></div>
  </div>
</div>

## Example

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="Checkbox example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="checkbox-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="checkbox-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="checkbox-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>field = sdk.ui.Checkbox(
    "components_test_forms_checkbox_store",
    "Checkbox",
    checked=bound.store("/components_test/forms/checkbox/store", scope="page", default=False),
)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="checkbox-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Checkbox
  id: components_test_forms_yaml_checkbox
  label: "Checkbox YAML"
  checked: {type: store, scope: page, path: /components_test/forms/checkbox/store, default: false}</code></pre></div>
  </div>
</div>

## Runtime

Use `collect_input_ids` to read `true` or `false`. Use `checked.set` property updates, `stateUpdate`, or `dataModelUpdate` to change the value from an action.
