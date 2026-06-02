# Action Dispatch

[<- Back to Components Index](./index.md)

Components dispatch actions through the runtime action dispatcher. Use this page when wiring `Button`, `Form`, `List`, `DataTable`, `Card`, or any nested action definition.

## Qualified Names

Module actions called from UI must use the fully qualified action name:

```text
module_name.action_name
```

The Python decorator keeps the local action name inside the module:

```python
from democrai.sdk.decorators import action

@action("test_button_echo")
async def test_button_echo(ctx: dict, session: dict, module_sdk):
    ...
```

The UI calls the same action with the module prefix:

```yaml
action: components.test_button_echo
```

Do not use only `test_button_echo` in a component definition. An unqualified module action can be dispatched as an unknown action.

Core runtime actions such as `open_drawer`, `close_drawer`, and `nav` are documented by the effect or navigation pages that use them. The `module.action` rule applies to module-defined actions.

## Navigation Contexts

Use `nav` for declarative route navigation. Navigation payloads that include a route `path` must also include `type: nav`:

```yaml
action:
  name: nav
  context:
    type: nav
    path: /system/index
```

`path` is also the shorthand key for implicit data-model bindings. The `type: nav` marker makes the payload structural and keeps route paths distinct from bindings in nested action contexts, item actions, tree nodes, and other component payloads. Do not rely on a `{path: ...}` context without the marker for route navigation.

## Action Shapes

For simple component actions, pass the qualified name as a string and use `params` for static context:

```yaml
- kind: Button
  id: run_import
  label: Run import
  action: components.test_button_echo
  params:
    source: toolbar
```

Nested actions use an action object with `name` and `context`:

```yaml
item_actions:
  - label: Open
    icon: ric.external-link-line
    action:
      name: components.test_list_action_event
      context:
        item_id: "$item.id"
```

`params` and `context` are merged into the action payload by the component that dispatches the action. Component-specific payload additions, such as selected rows or clicked items, are documented on the component page.

## Action Confirmation

Action objects can declare a client-side confirmation step with `confirm`. When present, the client asks for confirmation before dispatching the action. If the user cancels, no action is sent to the backend.

```yaml
action:
  name: components.button_confirm_action
  context:
    source: yaml_primary
  confirm:
    text: "@t/components.button.confirm.prompt"
    confirm_text: "@t/components.button.confirm.accept"
    cancel_text: "@t/components.button.confirm.cancel"
```

`confirm` belongs to the action object, not to the component. The same shape is used by simple component actions and nested action definitions. YAML confirmation text can use `@t/...` translation keys. Python-defined UI should pass strings already resolved through `sdk.i18n.t(...)`.

## Inputs And Loading

Components that collect mounted inputs include those values in the action payload:

```yaml
- kind: Button
  id: collect_title
  label: Collect input
  action: components.test_button_collect
  collect_input_ids: [title_input]
  track_loading: components.test_button_collect
```

When using `track_loading`, use the same qualified action name that the component dispatches. This lets the client match pending action state to the trigger.

## Nested Action Context

Nested action definitions keep the same naming rule:

- `List.itemActions`, `List.onItemClick`, and `List.selectedItemsAction` use qualified action names.
- `DataTable.row_actions` and `DataTable.selection_actions` use qualified action names.
- `Card.itemActions` use qualified action names.

When a component documents `$item.<field>`, that placeholder is resolved from the current item or row for that action. Use the placeholder only in components that document item-aware action context.

## Permissions

`required_permissions` on a component or nested action controls whether the UI renders that trigger. It does not replace backend authorization. Protect the action handler with the permission decorator required by the module.

## Troubleshooting

If the runtime reports `Unknown action`, check these points first:

- the component uses `module.action`, not just `action`
- the decorator name matches the action suffix used by the UI
- the module imports the file that defines the decorated action during startup
- `track_loading` uses the same qualified name as the dispatched action
