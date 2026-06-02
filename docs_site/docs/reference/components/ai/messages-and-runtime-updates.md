# AI Messages

[<- Back to AI Chat](./index.md)

## Purpose

Message timeline rendering, runtime message updates, component messages, scroll-driven history loading, and toolbar composition.

## Message Contract

`MessageList` is the main chat renderer. A message is a persistable timeline item.
Use `role` for who produced the item and `kind` for how the item should be rendered.

| Field | Web | Desktop | Notes |
|---|---|---|---|
| `id` | yes | yes | Required for reliable replace patches |
| `role` | yes | yes | Producer: `user`, `assistant`, `tool`, `system` |
| `kind` | yes | yes | Renderer kind: `text`, `component`, `tool_call`, `tool_result`, `task` |
| `status` | yes | yes | `pending`, `running`, `completed`, `failed`, `cancelled` |
| `content` | yes | yes | Kind-specific payload |
| `meta` | yes | yes | Footer metadata |
| `actions` | yes | yes | Per-message action buttons |
| `content.attachments` | yes | yes | Attachment payloads are passed to `on_attachment_click`; the module action decides how to handle them |
| `content.components` | yes | yes | A2UI components rendered flat for `kind: component` |

Text message example:

```python
message = {
    "id": "m_42",
    "role": "assistant",
    "kind": "text",
    "status": "completed",
    "content": {
        "text": "Here is the updated summary.",
        "reasoning": "I re-ranked the issues after checking the release notes.",
        "attachments": [
            {
                "name": "candidate-brief.pdf",
                "mime": "application/pdf",
                "source_path": "/abs/path/candidate-brief.pdf",
                "url": "https://example.invalid/candidate-brief.pdf",
            }
        ],
    },
    "meta": "assistant · 11:03",
}
```

Component message example:

```python
message = {
    "id": "m_chart_1",
    "role": "assistant",
    "kind": "component",
    "status": "completed",
    "content": {
        "components": [
            sdk.ui.Chart(
                "risk_chart",
                chart_type="bar",
                data=[21, 14, 8],
                labels=["High", "Medium", "Low"],
            ).to_dict()
        ]
    },
}
```

## MessageList Properties

| Property | Web | Desktop | Runtime update | Notes |
|---|---|---|---|---|
| `id` | yes | yes | no | Required |
| `messages` | yes | yes | yes | `append`, `prepend`, `remove`, `replace`, `set` supported |
| `on_attachment_click` | yes | yes | render-time | Action spec that receives attachment payload fields |
| `on_load_more` | yes | yes | render-time | Action spec emitted when the message scroll reaches the top |
| `style` | yes | yes | yes | Standard styling |

For application chat pages, keep toolbar controls outside the scrollable message area. `MessageList` should own message rendering and scroll behavior; buttons such as download, clear, pin, search, or thread actions should be normal components composed above or beside the `ScrollArea`.

## MessageItem Properties

Use `MessageItem` only for isolated single-message rendering. For real conversations prefer `MessageList`.

| Property | Web | Desktop | Runtime update | Notes |
|---|---|---|---|---|
| `id` | yes | yes | no | Required |
| `role` | yes | yes | no | `user`, `assistant`, `task` are meaningful |
| `text` | yes | yes | yes | Supported |
| `meta` | yes | yes | yes | Supported |
| `actions` | yes | yes | yes | Supported |

## Append Message

Append a new assistant message.

```python
new_message = {
    "id": "m_3",
    "role": "assistant",
    "kind": "text",
    "status": "completed",
    "content": {"text": "Here is the final summary."},
    "meta": "assistant · now",
}

return sdk.effects.respond(
    sdk.effects.ui_collection_append("support_messages", "messages", new_message)
)
```

## Prepend Older Messages

Prepend older messages loaded from storage.

```python
older_messages = [
    {
        "id": "m_1",
        "role": "user",
        "kind": "text",
        "status": "completed",
        "content": {"text": "Earlier question."},
    }
]

return sdk.effects.respond(
    sdk.effects.ui_collection_prepend("support_messages", "messages", older_messages)
)
```

For scroll-driven history loading, bind `on_load_more` and prepend the returned older messages.
The renderers preserve the visible scroll position when messages are prepended.

```yaml
- kind: MessageList
  id: support_messages
  messages: "@data/chat/messages"
  on_load_more:
    name: support.load_older_messages
    context: {target: support_messages}
```

Persisted chat history should remain backend-owned. Use `on_load_more` to request an older window from the backend, then patch the visible `MessageList` with `prepend`. Do not treat the client store as the primary chat database for long conversations.

For large or fast-changing chats, avoid binding the whole message history to a
reactive store. Render an initial window from backend state, then append,
prepend, replace, or remove items directly on `MessageList.messages` with
collection updates. This keeps desktop and web clients from rerendering the
entire timeline on every message.

## Replace Message

Replace an existing message.

```python
replacement = {
    "id": "m_3",
    "role": "assistant",
    "kind": "text",
    "status": "completed",
    "content": {
        "text": "Here is the corrected final summary.",
        "reasoning": "I re-checked the dependency list.",
    },
    "meta": "assistant · now",
}

return sdk.effects.respond(
    sdk.effects.ui_collection_replace(
        "support_messages",
        "messages",
        {"id": "m_3", "item": replacement},
    )
)
```

## Component Messages

Prefer `kind: component` for structured UI in chat timelines. The renderer does not wrap component messages in a chat bubble; the component controls its own visual framing. If the UI should look like a card, put a `Card` component in `content.components`.

Pattern:

1. Build a new message with `kind: component`.
2. Put one or more A2UI component dicts in `content.components`.
3. Append it to `MessageList.messages`.

```python
component_message = {
    "id": "m_10_component",
    "role": "assistant",
    "kind": "component",
    "status": "completed",
    "content": {
        "components": [
            sdk.ui.Card(
                "m_10_card",
                [sdk.ui.Text("m_10_card_text", "Runtime-appended content")],
                variant="outlined",
            ).to_dict()
        ]
    },
}

return sdk.effects.respond(
    sdk.effects.ui_collection_append("support_messages", "messages", component_message)
)
```

Use `messages.replace` with the same message `id` when a component message must be updated from persisted state.

## Chat Toolbar Pattern

A chat toolbar is regular layout composition, not a special `MessageList` feature.
Place it outside the scroll area so it remains reachable while the user navigates the timeline.

```yaml
- kind: Column
  id: support_chat
  children:
    - kind: Row
      id: support_chat_toolbar
      align: right
      children:
        - kind: Button
          id: support_download
          label: Download
          action:
            name: support.chat_toolbar
            context:
              command: download
              target: support_messages
    - kind: ScrollArea
      id: support_messages_scroll
      scroll_y: true
      scroll_x: false
      children:
        - kind: MessageList
          id: support_messages
          messages: []
```

The toolbar action decides what to do. In the showcase, the toolbar button emits a payload and the action displays it in a toast.

## Attachment Click Pattern

`on_attachment_click` sends the attachment payload to an action. The framework does not impose behavior on attachment clicks.

Expected payload fields:

- `message_id`
- `message_role`
- `name`
- `mime`
- `path`
- `source_path`
- `file_id`
- `url`

The receiving action owns the behavior. In the showcase, it displays the payload in a toast.
