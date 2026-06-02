# Select

[<- Back to Forms Components](./index.md)

`Select` lets the user choose one or more values from a declared option list.

## Contract

| Property | Type | Notes |
|---|---|---|
| `label` | `str` | Input label. |
| `options` | `list[dict]` | Option entries with `label` and `value`. |
| `value` | `Any` | Current selected value. Use `str` for single select and `list[str]` for `multiple=true`. |
| `placeholder` | `str` | Placeholder for the empty state. |
| `multiple` | `bool` | Enables multiple selected values. |
| `searchable` | `bool` | Select-level searchable flag. `Combobox` is the dedicated searchable single-select component. |
| `max_width` | `int | None` | Optional width constraint. |
| `action` / `params` | `str` or action object / `dict` | Optional action emitted on change. Action objects can include `confirm`. |

Value collected by actions: `str` when `multiple=false`, `list[str]` when `multiple=true`.

## Action Confirmation

Use an action object with `confirm` to require confirmation before the selection change action is dispatched. If the user cancels the dialog, no backend action is sent and the selection keeps its previous value.

The component test page exposes a select action counter and the last received payload so dispatch can be checked directly after confirming.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="select confirm example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="select-confirm-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="select-confirm-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="select-confirm-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>field = sdk.ui.Select(
    &quot;confirm_python_select&quot;,
    label=sdk.i18n.t(&quot;components.select.confirm.python_label&quot;),
    options=[
        {&quot;label&quot;: sdk.i18n.t(&quot;components.choice.confirm.option_alpha&quot;), &quot;value&quot;: &quot;alpha&quot;},
        {&quot;label&quot;: sdk.i18n.t(&quot;components.choice.confirm.option_beta&quot;), &quot;value&quot;: &quot;beta&quot;},
        {&quot;label&quot;: sdk.i18n.t(&quot;components.choice.confirm.option_gamma&quot;), &quot;value&quot;: &quot;gamma&quot;},
    ],
    value=&quot;alpha&quot;,
    placeholder=sdk.i18n.t(&quot;components.select.confirm.placeholder&quot;),
)
field.set_prop(
    &quot;action&quot;,
    {
        &quot;name&quot;: &quot;components.select_confirm_action&quot;,
        &quot;context&quot;: {&quot;source&quot;: &quot;python_select&quot;},
        &quot;confirm&quot;: {
            &quot;text&quot;: sdk.i18n.t(&quot;components.select.confirm.prompt&quot;),
            &quot;confirm_text&quot;: sdk.i18n.t(&quot;components.select.confirm.accept&quot;),
            &quot;cancel_text&quot;: sdk.i18n.t(&quot;components.select.confirm.cancel&quot;),
        },
    },
)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="select-confirm-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Select
  id: confirm_yaml_select
  label: &quot;@t/components.select.confirm.yaml_label&quot;
  value: alpha
  placeholder: &quot;@t/components.select.confirm.placeholder&quot;
  options:
    - label: &quot;@t/components.choice.confirm.option_alpha&quot;
      value: alpha
    - label: &quot;@t/components.choice.confirm.option_beta&quot;
      value: beta
    - label: &quot;@t/components.choice.confirm.option_gamma&quot;
      value: gamma
  action:
    name: components.select_confirm_action
    context:
      source: yaml_select
    confirm:
      text: &quot;@t/components.select.confirm.prompt&quot;
      confirm_text: &quot;@t/components.select.confirm.accept&quot;
      cancel_text: &quot;@t/components.select.confirm.cancel&quot;</code></pre></div>
  </div>
</div>

## Example

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="Select example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="select-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="select-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="select-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>options = [
    {"label": "Draft", "value": "draft"},
    {"label": "Published", "value": "published"},
    {"label": "Archived", "value": "archived"},
]

single = sdk.ui.Select(
    "components_test_forms_select_store",
    label="Select",
    options=options,
    value=bound.store("/components_test/forms/select/store", scope="page", default="draft"),
    placeholder="Choose status",
)

multiple = sdk.ui.Select(
    "components_test_forms_select_multiple_store",
    label="Select multiple",
    options=options,
    value=bound.store("/components_test/forms/select_multiple/store", scope="page", default=["draft", "archived"]),
    multiple=True,
)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="select-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Select
  id: components_test_forms_yaml_select
  label: "Select YAML"
  value: {type: store, scope: page, path: /components_test/forms/select/store, default: draft}
  options:
    - label: "Draft"
      value: draft
    - label: "Published"
      value: published

- kind: Select
  id: components_test_forms_yaml_select_multiple
  label: "Select multiple YAML"
  value: {type: store, scope: page, path: /components_test/forms/select_multiple/store, default: [draft, archived]}
  multiple: true
  options:
    - label: "Draft"
      value: draft
    - label: "Published"
      value: published
    - label: "Archived"
      value: archived</code></pre></div>
  </div>
</div>

## Runtime

Use `collect_input_ids` to read the selected value. Use `value.set` property updates, `stateUpdate`, or `dataModelUpdate` to change the selection from an action.
