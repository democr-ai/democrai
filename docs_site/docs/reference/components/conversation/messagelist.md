# MessageList

[<- Back to Conversation Components](./index.md)

## Purpose

Conversation message collection component. It renders the visible message window and owns scroll behavior; application toolbars and persistence live outside the component.

## Constructor

```python
MessageList(
    id: str,
    messages: Optional[List[Dict[str, Any]]] = None
)
```

## Constructor Parameters

| Python arg | Type | Default | YAML key(s) driven by this arg |
|---|---|---|---|
| `id` | `str` | `required` | `id` |
| `messages` | `Optional[List[Dict[str, Any]]]` | `None` | `messages` |

Common YAML/runtime properties:

| Property | Notes |
|---|---|
| `on_attachment_click` | ActionSpec emitted with attachment payload fields |
| `on_load_more` | ActionSpec emitted when the message scroll reaches the top |

## Action Confirmation

Message actions inside `messages[*].actions` and the list-level `on_attachment_click` callback accept ActionSpec objects with `confirm`. The client asks for confirmation before dispatching the action.

## Message Contract

`MessageList` renders persistable timeline items. `role` identifies the producer, while `kind` identifies the renderer behavior.

| Field | Notes |
|---|---|
| `id` | Stable message id; required for reliable replace/remove patches |
| `role` | Producer such as `user`, `assistant`, `tool`, or `system` |
| `kind` | `text`, `component`, `tool_call`, `tool_result`, or `task`; defaults to `text` |
| `status` | Optional lifecycle state such as `pending`, `running`, `completed`, `failed` |
| `content` | Kind-specific payload |

For `kind: text`, use `content.text`, `content.reasoning`, and `content.attachments`.
For `kind: component`, use `content.components` with A2UI component dictionaries. Component messages render flat in the timeline; add a `Card` component yourself when the content should be framed.

Attachment clicks do not imply built-in behavior. The renderer emits the payload to `on_attachment_click`; the module action decides what should happen.

<div class="docs-code-group" data-default-tab="python">
  <div class="docs-code-group__tabs" role="tablist" aria-label="MessageList confirm example">
    <button type="button" class="docs-code-group__tab" data-tab="python" aria-selected="true">Python</button>
    <button type="button" class="docs-code-group__tab" data-tab="yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" data-tab-panel="python">

```python
message_list = sdk.ui.MessageList(
    "messagelist_confirm",
    messages=[
        {
            "id": "message_alpha",
            "role": "assistant",
            "kind": "text",
            "status": "completed",
            "content": {
                "text": "Message list with confirmable action.",
                "attachments": [
                    {"name": "confirm-preview.pdf", "mime": "application/pdf", "path": "/tmp/confirm-preview.pdf"}
                ],
            },
            "meta": "ActionSpec confirm",
            "actions": [
                {
                    "label": sdk.i18n.t("components.messagelist.confirm.action_label"),
                    "icon": "ric.check-line",
                    "action": {
                        "name": "components.messagelist_confirm_action",
                        "context": {"source": "python_messagelist_action", "operation": "message_action"},
                        "confirm": {
                            "text": sdk.i18n.t("components.messagelist.confirm.action_prompt"),
                            "confirm_text": sdk.i18n.t("components.messagelist.confirm.accept"),
                            "cancel_text": sdk.i18n.t("components.messagelist.confirm.cancel"),
                        },
                    },
                }
            ],
        }
    ],
)
message_list.set_prop(
    "on_attachment_click",
    {
        "name": "components.messagelist_confirm_action",
        "context": {"source": "python_messagelist_attachment", "operation": "attachment_click"},
        "confirm": {
            "text": sdk.i18n.t("components.messagelist.confirm.attachment_prompt"),
            "confirm_text": sdk.i18n.t("components.messagelist.confirm.accept"),
            "cancel_text": sdk.i18n.t("components.messagelist.confirm.cancel"),
        },
    },
)
message_list.set_prop(
    "on_load_more",
    {
        "name": "components.load_older_messages",
        "context": {"target": "messagelist_confirm"},
    },
)
```

  </div>
  <div class="docs-code-group__panel" data-tab-panel="yaml">

```yaml
- kind: MessageList
  id: messagelist_confirm
  on_attachment_click:
    name: components.messagelist_confirm_action
    context:
      source: yaml_messagelist_attachment
      operation: attachment_click
    confirm:
      text: "@t/components.messagelist.confirm.attachment_prompt"
      confirm_text: "@t/components.messagelist.confirm.accept"
      cancel_text: "@t/components.messagelist.confirm.cancel"
  on_load_more:
    name: components.load_older_messages
    context:
      target: messagelist_confirm
  messages:
    - id: message_alpha
      role: assistant
      kind: text
      status: completed
      content:
        text: Message list with confirmable action.
        attachments:
          - name: confirm-preview.pdf
            mime: application/pdf
            path: /tmp/confirm-preview.pdf
      meta: ActionSpec confirm
      actions:
        - label: "@t/components.messagelist.confirm.action_label"
          icon: ric.check-line
          action:
            name: components.messagelist_confirm_action
            context:
              source: yaml_messagelist_action
              operation: message_action
            confirm:
              text: "@t/components.messagelist.confirm.action_prompt"
              confirm_text: "@t/components.messagelist.confirm.accept"
              cancel_text: "@t/components.messagelist.confirm.cancel"
```

  </div>
</div>

## Chat Toolbar Composition

Keep toolbar controls outside the scrollable message area. A toolbar is normal layout YAML and can contain buttons, menus, search inputs, filters, or export actions.

```yaml
- kind: Column
  id: chat_column
  children:
    - kind: Row
      id: chat_toolbar
      align: right
      children:
        - kind: Button
          id: chat_download
          label: Download
          action:
            name: chat.toolbar_action
            context: {command: download, target: chat_messages}
    - kind: ScrollArea
      id: chat_scroll
      scroll_y: true
      children:
        - kind: MessageList
          id: chat_messages
          messages: []
          on_load_more:
            name: chat.load_older_messages
            context: {target: chat_messages}
```

For long conversations, keep the canonical messages in backend storage. Use `on_load_more` to request older windows and prepend them into the visible list.

## Full Python Example

```python
import sdk

component = sdk.ui.MessageList(
    id='messagelist_1',
    messages=None,
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
- kind: MessageList
  id: messagelist_1
  messages: null
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
