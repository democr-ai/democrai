# RadioGroup

[<- Back to Forms Components](./index.md)

`RadioGroup` is a single-choice input rendered as a radio button group.

## Contract

| Property | Type | Notes |
|---|---|---|
| `label` | `str` | Group label. |
| `options` | `list[dict]` | Option entries with `label` and `value`. |
| `value` | `str` | Current selected option value. |
| `action` | action object | Optional action emitted on change. Action objects can include `confirm`. |
| `options_action` | `str | None` | Optional action source for options. |
| `options_store` | `str | None` | Optional store source for options. |

Value collected by actions: `str`.

## Action Confirmation

Use an action object with `confirm` to require confirmation before the radio selection action is dispatched. If the user cancels the dialog, no backend action is sent and the group keeps its previous value.

The component test page exposes a radio group action counter and the last received payload so dispatch can be checked directly after confirming.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="radiogroup confirm example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="radiogroup-confirm-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="radiogroup-confirm-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="radiogroup-confirm-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>field = sdk.ui.RadioGroup(
    &quot;confirm_python_radiogroup&quot;,
    sdk.i18n.t(&quot;components.radiogroup.confirm.python_label&quot;),
    options=[
        {&quot;label&quot;: sdk.i18n.t(&quot;components.choice.confirm.option_alpha&quot;), &quot;value&quot;: &quot;alpha&quot;},
        {&quot;label&quot;: sdk.i18n.t(&quot;components.choice.confirm.option_beta&quot;), &quot;value&quot;: &quot;beta&quot;},
        {&quot;label&quot;: sdk.i18n.t(&quot;components.choice.confirm.option_gamma&quot;), &quot;value&quot;: &quot;gamma&quot;},
    ],
    value=&quot;alpha&quot;,
)
field.set_prop(
    &quot;action&quot;,
    {
        &quot;name&quot;: &quot;components.radiogroup_confirm_action&quot;,
        &quot;context&quot;: {&quot;source&quot;: &quot;python_radiogroup&quot;},
        &quot;confirm&quot;: {
            &quot;text&quot;: sdk.i18n.t(&quot;components.radiogroup.confirm.prompt&quot;),
            &quot;confirm_text&quot;: sdk.i18n.t(&quot;components.radiogroup.confirm.accept&quot;),
            &quot;cancel_text&quot;: sdk.i18n.t(&quot;components.radiogroup.confirm.cancel&quot;),
        },
    },
)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="radiogroup-confirm-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: RadioGroup
  id: confirm_yaml_radiogroup
  label: &quot;@t/components.radiogroup.confirm.yaml_label&quot;
  value: alpha
  options:
    - label: &quot;@t/components.choice.confirm.option_alpha&quot;
      value: alpha
    - label: &quot;@t/components.choice.confirm.option_beta&quot;
      value: beta
    - label: &quot;@t/components.choice.confirm.option_gamma&quot;
      value: gamma
  action:
    name: components.radiogroup_confirm_action
    context:
      source: yaml_radiogroup
    confirm:
      text: &quot;@t/components.radiogroup.confirm.prompt&quot;
      confirm_text: &quot;@t/components.radiogroup.confirm.accept&quot;
      cancel_text: &quot;@t/components.radiogroup.confirm.cancel&quot;</code></pre></div>
  </div>
</div>

## Example

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="RadioGroup example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="radiogroup-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="radiogroup-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="radiogroup-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>field = sdk.ui.RadioGroup(
    "components_test_forms_radiogroup_store",
    "RadioGroup",
    options=[
        {"label": "Small", "value": "small"},
        {"label": "Medium", "value": "medium"},
        {"label": "Large", "value": "large"},
    ],
    value=bound.store("/components_test/forms/radiogroup/store", scope="page", default="small"),
)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="radiogroup-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: RadioGroup
  id: components_test_forms_yaml_radiogroup
  label: "RadioGroup YAML"
  value: {type: store, scope: page, path: /components_test/forms/radiogroup/store, default: small}
  options:
    - label: "Small"
      value: small
    - label: "Medium"
      value: medium
    - label: "Large"
      value: large</code></pre></div>
  </div>
</div>

## Runtime

Use `collect_input_ids` to read the selected option value. Use `value.set`, `stateUpdate`, or `dataModelUpdate` to change the selection from an action.
