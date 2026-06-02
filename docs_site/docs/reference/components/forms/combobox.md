# Combobox

[<- Back to Forms Components](./index.md)

`Combobox` is a single-select option input. It is built on the `Select` contract with `multiple=false` and `searchable=true`.

## Contract

| Property | Type | Notes |
|---|---|---|
| `label` | `str` | Input label. |
| `options` | `list[dict]` | Option entries with `label` and `value`. |
| `value` | `Any` | Current selected option value. |
| `placeholder` | `str` | Text shown before a value is selected. |
| `max_width` | `int | None` | Optional width constraint. |
| `action` / `params` | `str` or action object / `dict` | Optional action emitted on change. Action objects can include `confirm`. |

Value collected by actions: usually `str`.

## Action Confirmation

Use an action object with `confirm` to require confirmation before the combobox selection action is dispatched. If the user cancels the dialog, no backend action is sent and the combobox keeps its previous value.

The component test page exposes a combobox action counter and the last received payload so dispatch can be checked directly after confirming.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="combobox confirm example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="combobox-confirm-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="combobox-confirm-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="combobox-confirm-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>field = sdk.ui.Combobox(
    &quot;confirm_python_combobox&quot;,
    label=sdk.i18n.t(&quot;components.combobox.confirm.python_label&quot;),
    options=[
        {&quot;label&quot;: sdk.i18n.t(&quot;components.choice.confirm.option_alpha&quot;), &quot;value&quot;: &quot;alpha&quot;},
        {&quot;label&quot;: sdk.i18n.t(&quot;components.choice.confirm.option_beta&quot;), &quot;value&quot;: &quot;beta&quot;},
        {&quot;label&quot;: sdk.i18n.t(&quot;components.choice.confirm.option_gamma&quot;), &quot;value&quot;: &quot;gamma&quot;},
    ],
    value=&quot;alpha&quot;,
    placeholder=sdk.i18n.t(&quot;components.combobox.confirm.placeholder&quot;),
)
field.set_prop(
    &quot;action&quot;,
    {
        &quot;name&quot;: &quot;components.combobox_confirm_action&quot;,
        &quot;context&quot;: {&quot;source&quot;: &quot;python_combobox&quot;},
        &quot;confirm&quot;: {
            &quot;text&quot;: sdk.i18n.t(&quot;components.combobox.confirm.prompt&quot;),
            &quot;confirm_text&quot;: sdk.i18n.t(&quot;components.combobox.confirm.accept&quot;),
            &quot;cancel_text&quot;: sdk.i18n.t(&quot;components.combobox.confirm.cancel&quot;),
        },
    },
)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="combobox-confirm-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Combobox
  id: confirm_yaml_combobox
  label: &quot;@t/components.combobox.confirm.yaml_label&quot;
  value: alpha
  placeholder: &quot;@t/components.combobox.confirm.placeholder&quot;
  options:
    - label: &quot;@t/components.choice.confirm.option_alpha&quot;
      value: alpha
    - label: &quot;@t/components.choice.confirm.option_beta&quot;
      value: beta
    - label: &quot;@t/components.choice.confirm.option_gamma&quot;
      value: gamma
  action:
    name: components.combobox_confirm_action
    context:
      source: yaml_combobox
    confirm:
      text: &quot;@t/components.combobox.confirm.prompt&quot;
      confirm_text: &quot;@t/components.combobox.confirm.accept&quot;
      cancel_text: &quot;@t/components.combobox.confirm.cancel&quot;</code></pre></div>
  </div>
</div>

## Example

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="Combobox example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="combobox-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="combobox-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="combobox-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>field = sdk.ui.Combobox(
    "components_test_forms_combobox_store",
    label="Combobox",
    options=[
        {"label": "Rome", "value": "rome"},
        {"label": "Milan", "value": "milan"},
        {"label": "Turin", "value": "turin"},
    ],
    value=bound.store("/components_test/forms/combobox/store", scope="page", default="rome"),
    placeholder="Choose city",
)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="combobox-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Combobox
  id: components_test_forms_yaml_combobox
  label: "Combobox YAML"
  value: {type: store, scope: page, path: /components_test/forms/combobox/store, default: rome}
  placeholder: "Choose city"
  options:
    - label: "Rome"
      value: rome
    - label: "Milan"
      value: milan
    - label: "Turin"
      value: turin</code></pre></div>
  </div>
</div>

## Runtime

Use `collect_input_ids` to read the selected option value. `Combobox` is not a free-text field; the output is the selected option `value`.
