# Forms Components

[<- Back to Components Index](../index.md)

Forms components collect user input. Their values can be initialized from literals, page/global store bindings, or the current surface data model.

The input value shown by a component is not written back to store or data model automatically. Use `collect_input_ids` to read current values in an action, and return `stateUpdate`, `dataModelUpdate`, or property updates when the action must persist or change a value.

## Component List

- [Attachment](./attachment.md)
- [Button](./button.md)
- [Checkbox](./checkbox.md)
- [Combobox](./combobox.md)
- [DatePicker](./datepicker.md)
- [EditableList](./editablelist.md)
- [FolderSelector](./folderselector.md)
- [Form](./form.md)
- [RadioGroup](./radiogroup.md)
- [Select](./select.md)
- [Switch](./switch.md)
- [TagsInput](./tagsinput.md)
- [TextArea](./textarea.md)
- [TextField](./textfield.md)
- [Toggle](./toggle.md)

`Calendar` is documented in Complex because it is an event calendar, not an atomic form input.

## Value Shapes

| Component | Main value property | Collected type |
|---|---|---|
| `TextField` | `value` | `str` |
| `TextArea` | `value` | `str` |
| `Checkbox` | `checked` | `bool` |
| `Switch` | `checked` | `bool` |
| `Toggle` | `checked` | `bool` |
| `Select` | `value` | `str`, or `list[str]` with `multiple=true` |
| `TagsInput` | `value` | `list` |
| `EditableList` | `value` | `list[str]` |
| `Combobox` | `value` | `str` |
| `RadioGroup` | `value` | `str` |
| `DatePicker` | `value` | formatted `str` |
| `Attachment` | `value` | `list[dict]` |
| `FolderSelector` | `value` | `str` path |

## Reading Inputs

Buttons and actions can collect mounted input values by declaring `collect_input_ids`.

```python
button = sdk.ui.Button(
    "read_field",
    "Read",
    action="components.forms_test_read",
    params={
        "key": "textfield",
        "field_ids": ["components_test_forms_textfield_store"],
    },
)
button.set_property("collect_input_ids", ["components_test_forms_textfield_store"])
```

The action receives the input id as a key in `ctx`.

## Updating Values

Use `stateUpdate` when the value is bound to store.

```python
return sdk.effects.respond(
    sdk.effects.ui_messages([
        {
            "stateUpdate": {
                "scope": "page",
                "values": {
                    "/components_test/forms/textfield/store": "Published title",
                },
            }
        }
    ])
)
```

Use `dataModelUpdate` when the value is bound to the surface data model. Use direct property updates only when the target component declares the matching capability, such as `value.set` or `checked.set`.

## Visibility

Input components support the shared `show_if`, `hide_if`, and `required_permissions` contract. Visibility rules can observe store or data-model bindings. They do not read arbitrary input ids directly; if visibility must depend on an input value, update an observed store/data-model path from an action.
