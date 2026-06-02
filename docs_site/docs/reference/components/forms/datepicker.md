# DatePicker

[<- Back to Forms Components](./index.md)

`DatePicker` is a single date or date-time text input with format-aware masking.

## Contract

| Property | Type | Notes |
|---|---|---|
| `label` | `str` | Input label. |
| `value` | `str` | Current date value. Supports literal, store binding, and data-model binding. |
| `min_date` | `str` | Optional minimum accepted value. |
| `max_date` | `str` | Optional maximum accepted value. |
| `max_width` | `int | None` | Optional width constraint. |
| `format` | `str` | Default `yyyy-MM-dd`. Also supports tokens used by the renderer, such as `HH` and `mm`. |
| `action` / `params` | `str` or action object / `dict` | Optional action emitted on change. Action objects can include `confirm`. |

Value collected by actions: `str`.

## Action Confirmation

Use an action object with `confirm` to require confirmation before the date change action is dispatched. If the user cancels the dialog, no backend action is sent and the input keeps its previous value.

The component test page exposes a date picker action counter and the last received payload so dispatch can be checked directly after confirming.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="datepicker confirm example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="datepicker-confirm-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="datepicker-confirm-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="datepicker-confirm-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>field = sdk.ui.DatePicker(
    &quot;confirm_python_datepicker&quot;,
    label=sdk.i18n.t(&quot;components.datepicker.confirm.python_label&quot;),
    value=&quot;2026-04-29&quot;,
    min_date=&quot;2026-01-01&quot;,
    max_date=&quot;2026-12-31&quot;,
)
field.set_prop(
    &quot;action&quot;,
    {
        &quot;name&quot;: &quot;components.datepicker_confirm_action&quot;,
        &quot;context&quot;: {&quot;source&quot;: &quot;python_datepicker&quot;},
        &quot;confirm&quot;: {
            &quot;text&quot;: sdk.i18n.t(&quot;components.datepicker.confirm.prompt&quot;),
            &quot;confirm_text&quot;: sdk.i18n.t(&quot;components.datepicker.confirm.accept&quot;),
            &quot;cancel_text&quot;: sdk.i18n.t(&quot;components.datepicker.confirm.cancel&quot;),
        },
    },
)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="datepicker-confirm-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: DatePicker
  id: confirm_yaml_datepicker
  label: &quot;@t/components.datepicker.confirm.yaml_label&quot;
  value: &quot;2026-04-29&quot;
  min_date: &quot;2026-01-01&quot;
  max_date: &quot;2026-12-31&quot;
  action:
    name: components.datepicker_confirm_action
    context:
      source: yaml_datepicker
    confirm:
      text: &quot;@t/components.datepicker.confirm.prompt&quot;
      confirm_text: &quot;@t/components.datepicker.confirm.accept&quot;
      cancel_text: &quot;@t/components.datepicker.confirm.cancel&quot;</code></pre></div>
  </div>
</div>

## Example

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="DatePicker example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="datepicker-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="datepicker-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="datepicker-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>field = sdk.ui.DatePicker(
    "components_test_forms_datepicker_store",
    label="DatePicker",
    value=bound.store("/components_test/forms/datepicker/store", scope="page", default="2026-04-24"),
    min_date="2026-01-01",
    max_date="2026-12-31",
)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="datepicker-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: DatePicker
  id: components_test_forms_yaml_datepicker
  label: "DatePicker YAML"
  value: {type: store, scope: page, path: /components_test/forms/datepicker/store, default: "2026-04-24"}
  min_date: "2026-01-01"
  max_date: "2026-12-31"</code></pre></div>
  </div>
</div>

## Runtime

Use `collect_input_ids` to read the current formatted string. Use `value.set`, `stateUpdate`, or `dataModelUpdate` to change the value from an action.
