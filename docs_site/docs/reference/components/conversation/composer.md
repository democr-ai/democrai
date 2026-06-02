# Composer

[<- Back to Conversation Components](./index.md)

## Purpose

Conversation composer input for chat and LLM interaction flows. It emits user interaction payloads; the application action owns persistence and message timeline updates.

## Constructor

```python
Composer(
    id: str,
    placeholder: str = '',
    value: str = '',
    disabled: bool = False,
    multiline: bool = True,
    send_action: Optional[Any] = None,
    cancel_action: Optional[Any] = None,
    ingest: bool = True
)
```

## Constructor Parameters

| Python arg | Type | Default | YAML key(s) driven by this arg |
|---|---|---|---|
| `id` | `str` | `required` | `id` |
| `placeholder` | `str` | `''` | `placeholder` |
| `value` | `str` | `''` | `value` |
| `disabled` | `bool` | `False` | `disabled` |
| `multiline` | `bool` | `True` | `multiline` |
| `send_action` | `Optional[str \| dict]` | `None` | `send_action` |
| `cancel_action` | `Optional[str \| dict]` | `None` | `cancel_action` |
| `ingest` | `bool` | `True` | `ingest` |

When attachments are enabled, `ingest=false` prevents uploaded attachments from being enqueued for knowledge extraction.

Place the composer outside the message scroll area so it remains reachable while messages scroll.

## Model Runtime Props

The composer can expose runtime selections in its options menu. These props are passed through in the submit payload; the component does not resolve or execute tools, skills, or MCP servers.

| YAML key | Type | Submit key |
|---|---|---|
| `options` | `dict` | `options` as key/value entries |
| `options_schema` | `dict` | controls editable option fields |
| `options_editable` | `bool` | enables option editing |
| `tools` | `list[str \| dict]` | available tool choices |
| `skills` | `list[str \| dict]` | available skill choices |
| `mcp` | `list[str \| dict]` | available MCP server choices |
| `selected_tools` | `list[str]` | `selected_tools` |
| `selected_skills` | `list[str]` | `selected_skills` |
| `selected_mcp` | `list[str]` | `selected_mcp` |
| `tools_editable` | `bool` | enables tool selection |
| `skills_editable` | `bool` | enables skill selection |
| `mcp_editable` | `bool` | enables MCP selection |

Submit payload shape:

```json
{
  "intent": "submit",
  "component_id": "composer_id",
  "text": "message",
  "attachments": [],
  "options": [{"key": "temperature", "value": 0.7}],
  "selected_tools": [],
  "selected_skills": [],
  "selected_mcp": []
}
```

The submit action should usually persist/enqueue the user message on the backend, patch the visible `MessageList`, and clear the composer value with a property update. The composer does not automatically write user input back to store or append a message.

## Action Confirmation

`send_action` and `cancel_action` accept an ActionSpec object with `name`, `context`, and `confirm`. The confirmation is handled by the client before the action is dispatched. If the user cancels the dialog, the send or stop action is not emitted.

<div class="docs-code-group" data-default-tab="python">
  <div class="docs-code-group__tabs" role="tablist" aria-label="Composer confirm example">
    <button type="button" class="docs-code-group__tab" data-tab="python" aria-selected="true">Python</button>
    <button type="button" class="docs-code-group__tab" data-tab="yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" data-tab-panel="python">

```python
composer = sdk.ui.Composer(
    "composer_confirm",
    placeholder=sdk.i18n.t("components.composer.confirm.placeholder"),
    value="Python composer message",
    send_action={
        "name": "components.composer_confirm_action",
        "context": {"source": "python_composer"},
        "confirm": {
            "text": sdk.i18n.t("components.composer.confirm.prompt"),
            "confirm_text": sdk.i18n.t("components.composer.confirm.accept"),
            "cancel_text": sdk.i18n.t("components.composer.confirm.cancel"),
        },
    },
    cancel_action={
        "name": "components.composer_confirm_action",
        "context": {"source": "python_composer_stop"},
        "confirm": {
            "text": sdk.i18n.t("components.composer.confirm.stop_prompt"),
            "confirm_text": sdk.i18n.t("components.composer.confirm.accept"),
            "cancel_text": sdk.i18n.t("components.composer.confirm.cancel"),
        },
    },
)
composer.set_prop("stop_enabled", True)
```

  </div>
  <div class="docs-code-group__panel" data-tab-panel="yaml">

```yaml
- kind: Composer
  id: composer_confirm
  placeholder: "@t/components.composer.confirm.placeholder"
  value: YAML composer message
  stop_enabled: true
  send_action:
    name: components.composer_confirm_action
    context:
      source: yaml_composer
    confirm:
      text: "@t/components.composer.confirm.prompt"
      confirm_text: "@t/components.composer.confirm.accept"
      cancel_text: "@t/components.composer.confirm.cancel"
  cancel_action:
    name: components.composer_confirm_action
    context:
      source: yaml_composer_stop
    confirm:
      text: "@t/components.composer.confirm.stop_prompt"
      confirm_text: "@t/components.composer.confirm.accept"
      cancel_text: "@t/components.composer.confirm.cancel"
```

  </div>
</div>

## Full Python Example

```python
import sdk

component = sdk.ui.Composer(
    id='composer_1',
    placeholder='',
    value='',
    disabled=False,
    multiline=True,
    send_action=None,
    cancel_action=None,
)

component.set_required_permissions(['system.user.view'])
component.set_show_if({
    'mode': 'AND',
    'conditions': [
        {
            'left': {'type': 'store', 'scope': 'page', 'path': '/can_view'},
            'op': '==',
            'right': True,
        }
    ],
})
component.allow('visible.set', 'enabled.set')
```

## Full YAML Example

```yaml
- kind: Composer
  id: composer_1
  placeholder: ""
  value: ""
  disabled: false
  multiline: true
  send_action: null
  cancel_action: null
  required_permissions:
    - system.user.view
  show_if:
    mode: AND
    conditions:
      - left:
          type: store
          scope: page
          path: /can_view
        op: "=="
        right: true
  capabilities:
    - visible.set
    - enabled.set
```
