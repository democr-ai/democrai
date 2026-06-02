# FolderSelector

[<- Back to Forms Components](./index.md)

`FolderSelector` is a folder path input. On desktop it can integrate with native folder selection; on web it behaves as a path field because browser clients cannot browse arbitrary local folders.

## Contract

| Property | Type | Notes |
|---|---|---|
| `label` | `str` | Input label. |
| `value` | `str` | Current folder path. Supports literal, store binding, and data-model binding. |
| `placeholder` | `str` | Placeholder shown while empty. |
| `action` | `str` or action object | Optional action emitted on change. Action objects can include `confirm`. |

Value collected by actions: `str`.

## Action Confirmation

Use an action object with `confirm` to require confirmation before the folder path change is dispatched. If the user cancels the dialog, no backend action is sent and the folder path keeps its previous value.

The component test page exposes a folder selector action counter and the last received payload so dispatch can be checked directly after confirming.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="folderselector confirm example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="folderselector-confirm-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="folderselector-confirm-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="folderselector-confirm-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>field = sdk.ui.FolderSelector(
    &quot;confirm_python_folderselector&quot;,
    sdk.i18n.t(&quot;components.folderselector.confirm.python_label&quot;),
    value=&quot;/tmp&quot;,
    placeholder=sdk.i18n.t(&quot;components.folderselector.confirm.placeholder&quot;),
)
field.set_prop(
    &quot;action&quot;,
    {
        &quot;name&quot;: &quot;components.folderselector_confirm_action&quot;,
        &quot;context&quot;: {&quot;source&quot;: &quot;python_folderselector&quot;},
        &quot;confirm&quot;: {
            &quot;text&quot;: sdk.i18n.t(&quot;components.folderselector.confirm.prompt&quot;),
            &quot;confirm_text&quot;: sdk.i18n.t(&quot;components.folderselector.confirm.accept&quot;),
            &quot;cancel_text&quot;: sdk.i18n.t(&quot;components.folderselector.confirm.cancel&quot;),
        },
    },
)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="folderselector-confirm-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: FolderSelector
  id: confirm_yaml_folderselector
  label: &quot;@t/components.folderselector.confirm.yaml_label&quot;
  value: &quot;/tmp&quot;
  placeholder: &quot;@t/components.folderselector.confirm.placeholder&quot;
  action:
    name: components.folderselector_confirm_action
    context:
      source: yaml_folderselector
    confirm:
      text: &quot;@t/components.folderselector.confirm.prompt&quot;
      confirm_text: &quot;@t/components.folderselector.confirm.accept&quot;
      cancel_text: &quot;@t/components.folderselector.confirm.cancel&quot;</code></pre></div>
  </div>
</div>

## Example

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="FolderSelector example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="folderselector-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="folderselector-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="folderselector-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>field = sdk.ui.FolderSelector(
    "components_test_forms_folderselector_store",
    label="FolderSelector",
    value=bound.store("/components_test/forms/folderselector/store", scope="page", default="/tmp/demo"),
    placeholder="/tmp",
)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="folderselector-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: FolderSelector
  id: components_test_forms_yaml_folderselector
  label: "FolderSelector YAML"
  value: {type: store, scope: page, path: /components_test/forms/folderselector/store, default: "/tmp/demo"}
  placeholder: "/tmp"</code></pre></div>
  </div>
</div>

## Runtime

Use `collect_input_ids` to read the current path. Use `value.set`, `stateUpdate`, or `dataModelUpdate` to change the path from an action.
