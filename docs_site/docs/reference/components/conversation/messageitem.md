# MessageItem

[<- Back to Conversation Components](./index.md)

## Purpose

Single conversational message with role, text, metadata, and actions.

## Constructor

```python
MessageItem(
    id: str,
    role: str,
    text: str,
    meta: str = '',
    actions: Optional[List[Dict[str, Any]]] = None,
    reasoning: str = ''
)
```

## Constructor Parameters

| Python arg | Type | Default | YAML key(s) driven by this arg |
|---|---|---|---|
| `id` | `str` | `required` | `id` |
| `role` | `str` | `required` | `role` |
| `text` | `str` | `required` | `text` |
| `meta` | `str` | `''` | `meta` |
| `actions` | `Optional[List[Dict[str, Any]]]` | `None` | `actions` |
| `reasoning` | `str` | `''` | `reasoning` |

## Reasoning

`reasoning` carries model reasoning text separately from the final message text.
Clients can render it as a collapsible block while keeping `text` as the
assistant-visible answer.

## Action Confirmation

Each item in `actions` can define an ActionSpec under `action`. Add `confirm` to ask the user before the action is dispatched.

<div class="docs-code-group" data-default-tab="python">
  <div class="docs-code-group__tabs" role="tablist" aria-label="MessageItem confirm example">
    <button type="button" class="docs-code-group__tab" data-tab="python" aria-selected="true">Python</button>
    <button type="button" class="docs-code-group__tab" data-tab="yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" data-tab-panel="python">

```python
message = sdk.ui.MessageItem(
    "messageitem_confirm",
    role="assistant",
    text="Message item with confirmable action.",
    meta="ActionSpec confirm",
    actions=[
        {
            "label": sdk.i18n.t("components.messageitem.confirm.action_label"),
            "icon": "ric.check-line",
            "action": {
                "name": "components.messageitem_confirm_action",
                "context": {"source": "python_messageitem", "operation": "open"},
                "confirm": {
                    "text": sdk.i18n.t("components.messageitem.confirm.prompt"),
                    "confirm_text": sdk.i18n.t("components.messageitem.confirm.accept"),
                    "cancel_text": sdk.i18n.t("components.messageitem.confirm.cancel"),
                },
            },
        }
    ],
)
```

  </div>
  <div class="docs-code-group__panel" data-tab-panel="yaml">

```yaml
- kind: MessageItem
  id: messageitem_confirm
  role: assistant
  text: Message item with confirmable action.
  meta: ActionSpec confirm
  actions:
    - label: "@t/components.messageitem.confirm.action_label"
      icon: ric.check-line
      action:
        name: components.messageitem_confirm_action
        context:
          source: yaml_messageitem
          operation: open
        confirm:
          text: "@t/components.messageitem.confirm.prompt"
          confirm_text: "@t/components.messageitem.confirm.accept"
          cancel_text: "@t/components.messageitem.confirm.cancel"
```

  </div>
</div>

## Full Python Example

```python
import sdk

component = sdk.ui.MessageItem(
    id='messageitem_1',
    role='role value',
    text='text value',
    meta='',
    actions=None,
    reasoning='',
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
- kind: MessageItem
  id: messageitem_1
  role: role value
  text: text value
  meta: ""
  actions: null
  reasoning: ""
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
