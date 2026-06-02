# Form

[<- Back to Forms Components](./index.md)

`Form` renders a complete form from a schema in `model`. The component does not receive `TextField`, `Select`, `Attachment`, or other input components as children: the renderer creates those controls from the field definitions.

Use `Form` when a module needs a structured submit payload, client-side validation, field-level errors, loading state, and a predictable form layout.

## Contract

| Property | Type | Notes |
|---|---|---|
| `model` | `list[dict]` | Field and layout schema. |
| `values` | `dict` or binding | Initial values keyed by field `name`. Supports static values, store binding, and data-model binding. |
| `submit_label` | `str` | Submit button label. Defaults to `Submit`. |
| `action` | `str` or action object | Action called after successful client-side validation. Action objects can include `confirm`. |
| `params` | `dict` | Extra context merged into the submit action payload. |
| `track_loading` | `str` or `list[str]` | Action names used to show the submit loading state. |
| `errors` | `dict[str, str]` | Server-side field errors keyed by field `name`. |

`values` is used to initialize the fields. Editing the form does not automatically write the changed values back to store or data model. The updated values are sent to the submit action as one object under the form component id.

Module actions used by `action` and `track_loading` must be fully qualified, for example `components.forms_form_submit`. The Python decorator keeps the local action name, while the component dispatch uses `module.action`. See [Action Dispatch](../action-dispatch.md).

## Action Confirmation

Use an action object with `confirm` when the submit action must be confirmed after client-side validation and before backend dispatch. If validation fails, no confirmation dialog is shown. If the user cancels the dialog, no action is sent.

The component test page exposes a form submit counter and the last received form payload so the dispatch can be checked directly after confirming.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="form confirm example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="form-confirm-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="form-confirm-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="form-confirm-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>form = sdk.ui.Form(
    &quot;confirm_python_form&quot;,
    model=[
        {
            &quot;type&quot;: &quot;text&quot;,
            &quot;name&quot;: &quot;title&quot;,
            &quot;label&quot;: sdk.i18n.t(&quot;components.form.confirm.title_label&quot;),
            &quot;value&quot;: &quot;Python title&quot;,
            &quot;validations&quot;: [
                {
                    &quot;rule&quot;: &quot;required&quot;,
                    &quot;message&quot;: sdk.i18n.t(&quot;components.form.confirm.title_required&quot;),
                }
            ],
        },
        {
            &quot;type&quot;: &quot;textarea&quot;,
            &quot;name&quot;: &quot;notes&quot;,
            &quot;label&quot;: sdk.i18n.t(&quot;components.form.confirm.notes_label&quot;),
            &quot;value&quot;: &quot;Python notes&quot;,
        },
    ],
    submit_label=sdk.i18n.t(&quot;components.form.confirm.python_submit&quot;),
)
form.set_prop(
    &quot;action&quot;,
    {
        &quot;name&quot;: &quot;components.form_confirm_action&quot;,
        &quot;context&quot;: {&quot;source&quot;: &quot;python_form&quot;},
        &quot;confirm&quot;: {
            &quot;text&quot;: sdk.i18n.t(&quot;components.form.confirm.prompt&quot;),
            &quot;confirm_text&quot;: sdk.i18n.t(&quot;components.form.confirm.accept&quot;),
            &quot;cancel_text&quot;: sdk.i18n.t(&quot;components.form.confirm.cancel&quot;),
        },
    },
)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="form-confirm-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Form
  id: confirm_yaml_form
  submit_label: &quot;@t/components.form.confirm.yaml_submit&quot;
  action:
    name: components.form_confirm_action
    context:
      source: yaml_form
    confirm:
      text: &quot;@t/components.form.confirm.prompt&quot;
      confirm_text: &quot;@t/components.form.confirm.accept&quot;
      cancel_text: &quot;@t/components.form.confirm.cancel&quot;
  model:
    - type: text
      name: title
      label: &quot;@t/components.form.confirm.title_label&quot;
      value: YAML title
      validations:
        - rule: required
          message: &quot;@t/components.form.confirm.title_required&quot;
    - type: textarea
      name: notes
      label: &quot;@t/components.form.confirm.notes_label&quot;
      value: YAML notes</code></pre></div>
  </div>
</div>

## Model Structure

`model` is a list of nodes. Each node is either a layout node or a field node.

### Layout Nodes

| Key | Type | Notes |
|---|---|---|
| `type` | `row` or `column` | Defines the layout direction. |
| `children` | `list[dict]` | Child nodes. |
| `items` | `list[dict]` | Alternative name for `children`. |
| `spacing` | `int` | Gap between children. |
| `span` | `int` | Proportional size when the node is inside a row. |
| `stretch` | `int` | Alternative proportional size. |

Rows distribute children horizontally on desktop-sized surfaces and vertically on narrow web viewports. Use `span` or `stretch` on row children to control their relative width.

### Field Nodes

| Key | Type | Notes |
|---|---|---|
| `type` | `str` | Field renderer type. Unknown types fall back to text input. |
| `name` | `str` | Required. This is the key used in `values`, `errors`, and submit payload. |
| `label` | `str` | Field label. |
| `placeholder` | `str` | Placeholder for text-like inputs and select. |
| `value` | any | Field-level initial value. Usually supplied through `values` instead. |
| `span` | `int` | Proportional width inside a row. |
| `stretch` | `int` | Alternative proportional width inside a row. |
| `validations` | `list[dict]` | Client-side validation rules. |
| `show_if` | rule | Shows the field only when the rule evaluates to `true`. |
| `hide_if` | rule | Hides the field when the rule evaluates to `true`. |

## Field Visibility

Field nodes support `show_if` and `hide_if` inside `model`. These rules use the same grouped condition shape as component visibility, with one extra form-local binding: `$form.<field_name>`.

When a field is hidden, the form does not render it, does not validate it, does not materialize its attachments, and does not include it in the submit payload.

```yaml
- kind: Form
  id: reasoning_form
  action: system.save_reasoning_options
  model:
    - type: select
      name: reasoning_activation_type
      label: Activation type
      value: boolean
      options:
        - label: Boolean
          value: boolean
        - label: Select
          value: select
    - type: checkbox
      name: reasoning_enabled
      label: Enable reasoning
      show_if:
        conditions:
          - left: "$form.reasoning_activation_type"
            op: "=="
            right: boolean
    - type: select
      name: reasoning_effort
      label: Reasoning effort
      options:
        - label: Low
          value: low
        - label: Medium
          value: medium
      show_if:
        conditions:
          - left: "$form.reasoning_activation_type"
            op: "=="
            right: select
```

Use `show_if` for the positive case and `hide_if` for direct negative guards. If both are present, the field must pass `show_if` and must not match `hide_if`.

## Field Types

| Type | Rendered input | Main options | Collected value |
|---|---|---|---|
| `text` | TextField | `placeholder`, `validations` | `str` |
| `email` | TextField | `placeholder`, `validations` | `str` |
| `password` | TextField in password mode | `placeholder`, `validations` | `str` |
| `textarea` | TextArea | `placeholder`, `rows`, `auto_resize`, `validations` | `str` |
| `checkbox` | Checkbox | `validations` | `bool` |
| `toggle` | Toggle | `validations` | `bool` |
| `select` | Select | `options`, `multiple`, `placeholder`, `validations` | `str` or `list[str]` |
| `tags`, `tags_input` | TagsInput | `item_schema`, `placeholder`, `validations` | `list` |
| `editable_list` | EditableList | `item_schema`, `add_label`, `remove_label`, `submit_label`, `validations` | `list[str]` |
| `radio`, `radio_group` | RadioGroup | `options`, `validations` | `str` |
| `date` | DatePicker | `min_date`, `max_date`, `format`, `validations` | formatted `str` |
| `datetime`, `date_time` | DatePicker with date-time format | `min_date`, `max_date`, `format`, `validations` | formatted `str` |
| `attachment`, `file` | Attachment | `accept`, `multiple`, `validations` | `list[dict]` |

`Combobox` and `FolderSelector` are standalone form inputs. They are not part of the documented `Form.model` field set.

`tags` uses the `TagsInput` item schema. `editable_list` uses the `EditableList` item schema. Both field types are list-valued and can be validated with `required`.

## Schema Reference

The root `model` value is always a list. Each item must be a dict-like node.

### `row`

`row` groups children on the same horizontal line when the viewport has enough width.

| Key | Required | Type | Notes |
|---|---:|---|---|
| `type` | yes | `"row"` | Layout node type. |
| `children` | no | `list[dict]` | Child layout or field nodes. |
| `items` | no | `list[dict]` | Alternative to `children`. |
| `spacing` | no | `int` | Gap between children. |
| `span` | no | `int` | Proportional size when this row is itself inside another row. |
| `stretch` | no | `int` | Alternative to `span`. |

Each child inside a row can define `span` or `stretch`. If omitted, the child uses `1`.

### `column`

`column` groups children vertically.

| Key | Required | Type | Notes |
|---|---:|---|---|
| `type` | yes | `"column"` | Layout node type. |
| `children` | no | `list[dict]` | Child layout or field nodes. |
| `items` | no | `list[dict]` | Alternative to `children`. |
| `spacing` | no | `int` | Gap between children. |
| `span` | no | `int` | Proportional size when this column is inside a row. |
| `stretch` | no | `int` | Alternative to `span`. |

### Common Field Keys

These keys are accepted by every documented field type.

| Key | Required | Type | Notes |
|---|---:|---|---|
| `type` | yes | `str` | Field type. |
| `name` | yes | `str` | Key used inside `values`, `errors`, and the submitted form object. |
| `label` | no | `str` | Visible field label. Defaults to `name` in renderers that need a fallback. |
| `placeholder` | no | `str` | Used by text-like fields and select. |
| `value` | no | any | Field-level initial value. Root `values` usually supplies this instead. |
| `span` | no | `int` | Proportional width inside a row. |
| `stretch` | no | `int` | Alternative to `span`. |
| `validations` | no | `list[dict]` | Client-side validation rules. |
| `show_if` | no | rule | Shows the field only when the rule evaluates to `true`. Supports `$form.<field_name>`. |
| `hide_if` | no | rule | Hides the field when the rule evaluates to `true`. Supports `$form.<field_name>`. |

### `text`

| Key | Required | Type | Notes |
|---|---:|---|---|
| `type` | yes | `"text"` | Text input. |
| `name` | yes | `str` | Key in the submitted form object. |
| `label` | no | `str` | Field label. |
| `placeholder` | no | `str` | Empty-state hint. |
| `value` | no | `str` | Initial value. |
| `validations` | no | `list[dict]` | Supports `required`, `regex`, `min_length`, `max_length`, `equals_field`, `same_as`. |

### `email`

Same schema as `text`, with `type: "email"`. The component does not add a built-in email rule; define `regex` when the format must be enforced.

### `password`

Same schema as `text`, with `type: "password"`. The input is rendered in password mode.

### `textarea`

| Key | Required | Type | Notes |
|---|---:|---|---|
| `type` | yes | `"textarea"` | Multiline text input. |
| `name` | yes | `str` | Key in the submitted form object. |
| `label` | no | `str` | Field label. |
| `placeholder` | no | `str` | Empty-state hint. |
| `value` | no | `str` | Initial value. |
| `rows` | no | `int` | Initial row count. Defaults to `3` in the renderer. |
| `auto_resize` | no | `bool` | TextArea auto-resize flag. |
| `validations` | no | `list[dict]` | Supports text validation rules. |

### `checkbox`

| Key | Required | Type | Notes |
|---|---:|---|---|
| `type` | yes | `"checkbox"` | Boolean checkbox. |
| `name` | yes | `str` | Key in the submitted form object. |
| `label` | no | `str` | Field label. |
| `value` | no | `bool` | Initial checked state. |
| `validations` | no | `list[dict]` | `required` requires the value to be `true`. |

### `toggle`

Same schema as `checkbox`, with `type: "toggle"`.

### `select`

| Key | Required | Type | Notes |
|---|---:|---|---|
| `type` | yes | `"select"` | Select input. |
| `name` | yes | `str` | Key in the submitted form object. |
| `label` | no | `str` | Field label. |
| `placeholder` | no | `str` | Empty-state hint. |
| `value` | no | `str` or `list[str]` | Initial selected value. Use a list when `multiple` is `true`. |
| `options` | no | `list[dict]` | Each option has `label` and `value`. |
| `multiple` | no | `bool` | Enables multi-select and list values. |
| `validations` | no | `list[dict]` | `required` rejects empty selection. |

### `radio` / `radio_group`

| Key | Required | Type | Notes |
|---|---:|---|---|
| `type` | yes | `"radio"` or `"radio_group"` | RadioGroup input. |
| `name` | yes | `str` | Key in the submitted form object. |
| `label` | no | `str` | Field label. |
| `value` | no | `str` | Initial selected value. |
| `options` | no | `list[dict]` | Each option has `label` and `value`. |
| `validations` | no | `list[dict]` | Supports `required` and string comparison rules. |

### `date`

| Key | Required | Type | Notes |
|---|---:|---|---|
| `type` | yes | `"date"` | DatePicker input. |
| `name` | yes | `str` | Key in the submitted form object. |
| `label` | no | `str` | Field label. |
| `value` | no | `str` | Initial formatted date. |
| `format` | no | `str` | Defaults to `yyyy-MM-dd`. |
| `min_date` | no | `str` | Minimum selectable date. |
| `max_date` | no | `str` | Maximum selectable date. |
| `validations` | no | `list[dict]` | Supports common validation rules. |

### `datetime` / `date_time`

Same schema as `date`, with `type: "datetime"` or `type: "date_time"`. The default format is `yyyy-MM-dd HH:mm`.

### `attachment` / `file`

| Key | Required | Type | Notes |
|---|---:|---|---|
| `type` | yes | `"attachment"` or `"file"` | Attachment input. |
| `name` | yes | `str` | Key in the submitted form object. |
| `label` | no | `str` | Field label. |
| `value` | no | `list[dict]` | Initial attachment entries. |
| `accept` | no | `str` | Accepted extensions or MIME types. |
| `multiple` | no | `bool` | Allows more than one attachment. |
| `ingest` | no | `bool` | Defaults to `true`. When `false`, uploaded files are not enqueued for knowledge extraction. |
| `validations` | no | `list[dict]` | `required` rejects an empty list. |

## Option Shapes

`select` and `radio` options use this shape:

```python
{"label": "Admin", "value": "admin"}
```

For `select` with `multiple: true`, the value must be a list.

```python
{"type": "select", "name": "interests", "multiple": True, "options": interest_options}
```

For `attachment` and `file`, `accept` contains the accepted extensions or MIME types and `multiple` controls whether the value can contain more than one entry.

```python
{"type": "attachment", "name": "attachments", "accept": ".pdf,.txt", "multiple": True}
```

## Validation

Field definitions can include `validations`.

| Rule | Required keys | Meaning |
|---|---|---|
| `required` | `message` | Value must be present. For checkbox/toggle it must be `true`. |
| `regex` | `pattern`, `message` | String value must match the regular expression. Empty values are handled by `required`. |
| `min_length` | `value`, `message` | String or list must have at least `value` chars/items. |
| `max_length` | `value`, `message` | String or list must have at most `value` chars/items. |
| `equals_field`, `same_as` | `field` or `value`, `message` | Value must equal another field value. |

Client-side validation runs before submit. If validation fails, the submit action is not called.

## Values

`values` can be a static dict, a store binding, or a data-model binding.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="Form values">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="form-values-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="form-values-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="form-values-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>form_values = {
    "first_name": "Ada",
    "last_name": "Lovelace",
    "email": "ada@example.com",
    "role": "admin",
    "interests": ["ai", "docs"],
    "terms": True,
}

static_form = sdk.ui.Form(
    "components_test_form_static",
    model=form_model,
    values=form_values,
    submit_label="Submit static-values form",
    action="components.forms_form_submit",
    params={"output_key": "output_static"},
)

store_form = sdk.ui.Form(
    "components_test_form_store",
    model=form_model,
    values=bound.store("/components_test/form/values", scope="page", default=form_values),
    submit_label="Submit store-bound form",
    action="components.forms_form_submit",
    params={"output_key": "output_store"},
)

data_form = sdk.ui.Form(
    "components_test_form_data",
    model=form_model,
    values=bound.data("/components_test/form_model/values", default=form_values),
    submit_label="Submit data-model-bound form",
    action="components.forms_form_submit",
    params={"output_key": "output_data"},
)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="form-values-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Form
  id: components_test_form_yaml_static
  model: *form_model
  values: *form_values
  submit_label: "Submit YAML static-values form"
  action: components.forms_form_submit
  params:
    output_key: output_yaml_static

- kind: Form
  id: components_test_form_yaml_store
  model: *form_model
  values: {type: store, scope: page, path: /components_test/form/values, default: *form_values}
  submit_label: "Submit YAML store-bound form"
  action: components.forms_form_submit
  params:
    output_key: output_yaml_store

- kind: Form
  id: components_test_form_yaml_data
  model: *form_model
  values: "@data/components_test/form_model/values"
  submit_label: "Submit YAML data-model-bound form"
  action: components.forms_form_submit
  params:
    output_key: output_yaml_data</code></pre></div>
  </div>
</div>

## Complete Model Example

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="Form model example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="form-model-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="form-model-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="form-model-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>form_model = [
    {
        "type": "row",
        "spacing": 16,
        "children": [
            {
                "type": "text",
                "name": "first_name",
                "label": "First name",
                "placeholder": "Ada",
                "span": 1,
                "validations": [{"rule": "required", "message": "First name is required."}],
            },
            {
                "type": "text",
                "name": "last_name",
                "label": "Last name",
                "placeholder": "Lovelace",
                "span": 1,
                "validations": [{"rule": "required", "message": "Last name is required."}],
            },
        ],
    },
    {
        "type": "row",
        "spacing": 16,
        "children": [
            {
                "type": "email",
                "name": "email",
                "label": "Email",
                "span": 2,
                "validations": [
                    {"rule": "required", "message": "Email is required."},
                    {"rule": "regex", "pattern": r"^[^@\s]+@[^@\s]+\.[^@\s]+$", "message": "Use a valid email address."},
                ],
            },
            {
                "type": "password",
                "name": "password",
                "label": "Password",
                "span": 1,
                "validations": [{"rule": "min_length", "value": 6, "message": "Use at least 6 characters."}],
            },
        ],
    },
    {
        "type": "textarea",
        "name": "bio",
        "label": "Bio",
        "rows": 3,
        "validations": [{"rule": "max_length", "value": 180, "message": "Keep the bio under 180 characters."}],
    },
    {
        "type": "row",
        "spacing": 16,
        "children": [
            {
                "type": "select",
                "name": "role",
                "label": "Role",
                "options": [
                    {"label": "User", "value": "user"},
                    {"label": "Editor", "value": "editor"},
                    {"label": "Admin", "value": "admin"},
                ],
            },
            {
                "type": "select",
                "name": "interests",
                "label": "Interests",
                "multiple": True,
                "options": [
                    {"label": "AI", "value": "ai"},
                    {"label": "Docs", "value": "docs"},
                    {"label": "Automation", "value": "automation"},
                ],
            },
            {
                "type": "radio",
                "name": "plan",
                "label": "Plan",
                "options": [
                    {"label": "Free", "value": "free"},
                    {"label": "Pro", "value": "pro"},
                    {"label": "Enterprise", "value": "enterprise"},
                ],
            },
        ],
    },
    {
        "type": "row",
        "spacing": 16,
        "children": [
            {"type": "date", "name": "start_date", "label": "Start date", "min_date": "2026-01-01", "max_date": "2026-12-31"},
            {"type": "datetime", "name": "meeting_at", "label": "Meeting", "format": "yyyy-MM-dd HH:mm"},
        ],
    },
    {"type": "attachment", "name": "attachments", "label": "Attachments", "accept": ".pdf,.txt", "multiple": True, "ingest": True},
    {
        "type": "row",
        "spacing": 16,
        "children": [
            {"type": "checkbox", "name": "terms", "label": "Accept terms", "validations": [{"rule": "required", "message": "Terms must be accepted."}]},
            {"type": "toggle", "name": "newsletter", "label": "Newsletter"},
        ],
    },
]</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="form-model-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>model: &form_model
  - type: row
    spacing: 16
    children:
      - type: text
        name: first_name
        label: "First name"
        placeholder: "Ada"
        span: 1
        validations:
          - rule: required
            message: "First name is required."
      - type: text
        name: last_name
        label: "Last name"
        placeholder: "Lovelace"
        span: 1
        validations:
          - rule: required
            message: "Last name is required."
  - type: row
    spacing: 16
    children:
      - type: email
        name: email
        label: "Email"
        span: 2
        validations:
          - rule: required
            message: "Email is required."
          - rule: regex
            pattern: '^[^@\s]+@[^@\s]+\.[^@\s]+$'
            message: "Use a valid email address."
      - type: password
        name: password
        label: "Password"
        span: 1
        validations:
          - rule: min_length
            value: 6
            message: "Use at least 6 characters."
  - type: textarea
    name: bio
    label: "Bio"
    rows: 3
    validations:
      - rule: max_length
        value: 180
        message: "Keep the bio under 180 characters."
  - type: row
    spacing: 16
    children:
      - type: select
        name: role
        label: "Role"
        options:
          - {label: "User", value: user}
          - {label: "Editor", value: editor}
          - {label: "Admin", value: admin}
      - type: select
        name: interests
        label: "Interests"
        multiple: true
        options:
          - {label: "AI", value: ai}
          - {label: "Docs", value: docs}
          - {label: "Automation", value: automation}
      - type: radio
        name: plan
        label: "Plan"
        options:
          - {label: "Free", value: free}
          - {label: "Pro", value: pro}
          - {label: "Enterprise", value: enterprise}
  - type: row
    spacing: 16
    children:
      - {type: date, name: start_date, label: "Start date", min_date: "2026-01-01", max_date: "2026-12-31"}
      - {type: datetime, name: meeting_at, label: "Meeting", format: "yyyy-MM-dd HH:mm"}
  - type: attachment
    name: attachments
    label: "Attachments"
    accept: ".pdf,.txt"
    ingest: true
    multiple: true
  - type: row
    spacing: 16
    children:
      - type: checkbox
        name: terms
        label: "Accept terms"
        validations:
          - rule: required
            message: "Terms must be accepted."
      - type: toggle
        name: newsletter
        label: "Newsletter"</code></pre></div>
  </div>
</div>

## Submit Payload

The submit action receives:

- `form_id`
- the full values dict under `ctx[form_id]`
- every key from `params`

```python
@action("forms_form_submit")
async def forms_form_submit(ctx: dict, session: dict, sdk) -> dict:
    form_id = ctx.get("form_id")
    values = ctx.get(form_id, {})
    payload = {
        "form_id": form_id,
        "form_values": values,
        "output_key": ctx.get("output_key"),
    }
    return sdk.effects.respond(
        sdk.effects.ui_messages([
            {
                "stateUpdate": {
                    "scope": "page",
                    "values": {
                        "/components_test/form/output_static": json.dumps(payload),
                    },
                }
            }
        ])
    )
```

## Visibility And Permissions

`Form` supports the shared `show_if`, `hide_if`, and `required_permissions` contract.

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="Form visibility example">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="form-visibility-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="form-visibility-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="form-visibility-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>form.set_show_if({
    "conditions": [
        {"left": bound.store("/components_test/form/show", scope="page", default=True), "op": "==", "right": True}
    ]
})
form.set_hide_if({
    "conditions": [
        {"left": bound.store("/components_test/form/hide", scope="page", default=False), "op": "==", "right": True}
    ]
})
form.set_required_permissions(["components.forms.submit"])</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="form-visibility-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>show_if:
  conditions:
    - left: {type: store, scope: page, path: /components_test/form/show, default: true}
      op: "=="
      right: true
hide_if:
  conditions:
    - left: {type: store, scope: page, path: /components_test/form/hide, default: false}
      op: "=="
      right: true
required_permissions: [components.forms.submit]</code></pre></div>
  </div>
</div>

## Practical Rules

- Use `model` for field structure; do not pass input components as children.
- Use `values` to prefill create/edit forms from static data, page/global store, or the surface data model.
- Use `row` and `column` nodes as the first-level layout containers when the form needs predictable field distribution.
- Use `validations` for client-side blocking validation.
- Use `errors` for server-side field errors keyed by field `name`.
- Use the submit action for persistence; `Form` does not automatically persist edited values to store or data model.
