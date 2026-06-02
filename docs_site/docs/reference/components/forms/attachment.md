# Attachment

[<- Back to Forms Components](./index.md)

`Attachment` is a file input component. It represents selected files as a list of attachment dictionaries.

## Contract

| Property | Type | Notes |
|---|---|---|
| `label` | `str` | Input label. |
| `accept` | `str` | Browser file accept filter, such as `.pdf,.txt`. |
| `multiple` | `bool` | Allows more than one file. |
| `ingest` | `bool` | Defaults to `true`. When `false`, uploaded files are not enqueued for knowledge extraction. |
| `value` | `list[dict]` | Current attachment entries. |
| `action` / `params` | `str` or action object / `dict` | Optional action emitted on change. Action objects can include `confirm`. |

Value collected by actions: `list[dict]`.

## Action Confirmation

Use an action object with `confirm` to require confirmation before the attachment list change is dispatched. If the user cancels the dialog, no backend action is sent and the attachment list keeps its previous value.

The component test page exposes an attachment action counter and the last received payload so dispatch can be checked directly after confirming.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="attachment confirm example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="attachment-confirm-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="attachment-confirm-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="attachment-confirm-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>field = sdk.ui.Attachment(
    &quot;confirm_python_attachment&quot;,
    label=sdk.i18n.t(&quot;components.attachment.confirm.python_label&quot;),
    accept=&quot;.txt,.pdf,image/*&quot;,
    multiple=True,
)
field.set_prop(
    &quot;action&quot;,
    {
        &quot;name&quot;: &quot;components.attachment_confirm_action&quot;,
        &quot;context&quot;: {&quot;source&quot;: &quot;python_attachment&quot;},
        &quot;confirm&quot;: {
            &quot;text&quot;: sdk.i18n.t(&quot;components.attachment.confirm.prompt&quot;),
            &quot;confirm_text&quot;: sdk.i18n.t(&quot;components.attachment.confirm.accept&quot;),
            &quot;cancel_text&quot;: sdk.i18n.t(&quot;components.attachment.confirm.cancel&quot;),
        },
    },
)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="attachment-confirm-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Attachment
  id: confirm_yaml_attachment
  label: &quot;@t/components.attachment.confirm.yaml_label&quot;
  accept: &quot;.txt,.pdf,image/*&quot;
  multiple: true
  value: []
  action:
    name: components.attachment_confirm_action
    context:
      source: yaml_attachment
    confirm:
      text: &quot;@t/components.attachment.confirm.prompt&quot;
      confirm_text: &quot;@t/components.attachment.confirm.accept&quot;
      cancel_text: &quot;@t/components.attachment.confirm.cancel&quot;</code></pre></div>
  </div>
</div>

## Example

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="Attachment example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="attachment-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="attachment-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="attachment-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>field = sdk.ui.Attachment(
    "components_test_forms_attachment_store",
    label="Attachment",
    accept=".pdf,.txt",
    multiple=True,
    value=bound.store("/components_test/forms/attachment/store", scope="page", default=[]),
)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="attachment-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Attachment
  id: components_test_forms_yaml_attachment
  label: "Attachment YAML"
  value: {type: store, scope: page, path: /components_test/forms/attachment/store, default: []}
  accept: ".pdf,.txt"
  ingest: true
  multiple: true</code></pre></div>
  </div>
</div>

## Runtime

Use `collect_input_ids` to read the current attachment list. Use `value.set`, `value.append`, `value.remove`, `stateUpdate`, or `dataModelUpdate` depending on whether the action replaces or mutates the list.
