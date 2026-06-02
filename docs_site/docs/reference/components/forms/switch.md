# Switch

[<- Back to Forms Components](./index.md)

`Switch` is a boolean form input with switch-style presentation. Use it for enabled/disabled settings or other immediate yes/no choices.

## Contract

| Property | Type | Notes |
|---|---|---|
| `label` | `str` | Text shown next to the switch. |
| `checked` | `bool` | Current boolean state. Supports literal, store binding, and data-model binding. |
| `action` | `str` or action object | Optional action emitted on change. Action objects can include `confirm`. |
| `params` | `dict` | Optional action context. |

Value collected by actions: `bool`.

## Action Confirmation

Use an action object with `confirm` to require confirmation before the switch change action is dispatched. If the user cancels the dialog, no backend action is sent and the switch keeps its previous state.

The component test page exposes a switch action counter and the last received payload so dispatch can be checked directly after confirming.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="switch confirm example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="switch-confirm-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="switch-confirm-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="switch-confirm-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>field = sdk.ui.Switch(
    &quot;confirm_python_switch&quot;,
    sdk.i18n.t(&quot;components.switch.confirm.python_label&quot;),
    checked=False,
)
field.set_prop(
    &quot;action&quot;,
    {
        &quot;name&quot;: &quot;components.switch_confirm_action&quot;,
        &quot;context&quot;: {&quot;source&quot;: &quot;python_switch&quot;},
        &quot;confirm&quot;: {
            &quot;text&quot;: sdk.i18n.t(&quot;components.switch.confirm.prompt&quot;),
            &quot;confirm_text&quot;: sdk.i18n.t(&quot;components.switch.confirm.accept&quot;),
            &quot;cancel_text&quot;: sdk.i18n.t(&quot;components.switch.confirm.cancel&quot;),
        },
    },
)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="switch-confirm-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Switch
  id: confirm_yaml_switch
  label: &quot;@t/components.switch.confirm.yaml_label&quot;
  checked: false
  action:
    name: components.switch_confirm_action
    context:
      source: yaml_switch
    confirm:
      text: &quot;@t/components.switch.confirm.prompt&quot;
      confirm_text: &quot;@t/components.switch.confirm.accept&quot;
      cancel_text: &quot;@t/components.switch.confirm.cancel&quot;</code></pre></div>
  </div>
</div>

## Example

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="Switch example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="switch-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="switch-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="switch-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>field = sdk.ui.Switch(
    "components_test_forms_switch_store",
    "Switch",
    checked=bound.store("/components_test/forms/switch/store", scope="page", default=False),
)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="switch-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Switch
  id: components_test_forms_yaml_switch
  label: "Switch YAML"
  checked: {type: store, scope: page, path: /components_test/forms/switch/store, default: false}</code></pre></div>
  </div>
</div>

## Runtime

Use `collect_input_ids` to read `true` or `false`. Use `checked.set` property updates, `stateUpdate`, or `dataModelUpdate` to change the value from an action.
