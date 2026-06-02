# Toggle

[<- Back to Forms Components](./index.md)

`Toggle` is a boolean input rendered as a switch-style control. Use it for settings and immediate on/off state.

## Contract

| Property | Type | Notes |
|---|---|---|
| `label` | `str` | Text shown next to the control. |
| `checked` | `bool` | Current boolean state. Supports literal, store binding, and data-model binding. |
| `action` | `str` or action object | Optional action emitted on change. Action objects can include `confirm`. |
| `params` | `dict` | Optional action context. |

Value collected by actions: `bool`.

## Action Confirmation

Use an action object with `confirm` to require confirmation before the toggle change action is dispatched. If the user cancels the dialog, no backend action is sent and the toggle keeps its previous state.

The component test page exposes a toggle action counter and the last received payload so dispatch can be checked directly after confirming.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="toggle confirm example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="toggle-confirm-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="toggle-confirm-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="toggle-confirm-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>field = sdk.ui.Toggle(
    &quot;confirm_python_toggle&quot;,
    sdk.i18n.t(&quot;components.toggle.confirm.python_label&quot;),
    checked=False,
)
field.set_prop(
    &quot;action&quot;,
    {
        &quot;name&quot;: &quot;components.toggle_confirm_action&quot;,
        &quot;context&quot;: {&quot;source&quot;: &quot;python_toggle&quot;},
        &quot;confirm&quot;: {
            &quot;text&quot;: sdk.i18n.t(&quot;components.toggle.confirm.prompt&quot;),
            &quot;confirm_text&quot;: sdk.i18n.t(&quot;components.toggle.confirm.accept&quot;),
            &quot;cancel_text&quot;: sdk.i18n.t(&quot;components.toggle.confirm.cancel&quot;),
        },
    },
)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="toggle-confirm-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Toggle
  id: confirm_yaml_toggle
  label: &quot;@t/components.toggle.confirm.yaml_label&quot;
  checked: false
  action:
    name: components.toggle_confirm_action
    context:
      source: yaml_toggle
    confirm:
      text: &quot;@t/components.toggle.confirm.prompt&quot;
      confirm_text: &quot;@t/components.toggle.confirm.accept&quot;
      cancel_text: &quot;@t/components.toggle.confirm.cancel&quot;</code></pre></div>
  </div>
</div>

## Example

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="Toggle example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="toggle-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="toggle-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="toggle-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>field = sdk.ui.Toggle(
    "components_test_forms_toggle_store",
    "Toggle",
    checked=bound.store("/components_test/forms/toggle/store", scope="page", default=False),
)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="toggle-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Toggle
  id: components_test_forms_yaml_toggle
  label: "Toggle YAML"
  checked: {type: store, scope: page, path: /components_test/forms/toggle/store, default: false}</code></pre></div>
  </div>
</div>

## Runtime

Use `collect_input_ids` to read `true` or `false`. Use `checked.set` property updates, `stateUpdate`, or `dataModelUpdate` to change the value from an action.
