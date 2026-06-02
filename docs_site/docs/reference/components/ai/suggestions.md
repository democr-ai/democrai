# AI Suggestions

[<- Back to AI Chat](./index.md)

`Suggestions` is the quick-entry component for prompt chips or follow-up actions.

## Rooted YAML Example

```yaml
- kind: Column
  id: support_chat
  children:
    - kind: ScrollArea
      id: support_messages_scroll
      scroll_y: true
      children:
        - kind: MessageList
          id: support_messages
          messages: []
    - kind: Suggestions
      id: support_suggestions
      suggestions:
        - label: Summarize the thread
          prompt: Summarize the current thread
        - label: Extract tasks
          prompt: Extract all open tasks
      action:
        name: support.apply_suggestion
        context: {}
    - kind: Composer
      id: support_composer
      placeholder: Write a message...
      send_action:
        name: support.send_message
        context: {target: support_messages}
```

## Parameters

| Property | Web | Desktop | Runtime update | Notes |
|---|---|---|---|---|
| `id` | yes | yes | no | Required |
| `suggestions` | yes | yes | yes | Collection patch supported |
| `action` | yes | yes | render-time | Receives prompt, label, suggestion |
| `style` | yes | yes | yes | Standard styling |

## Example

```python
suggestions = sdk.ui.Suggestions(
    "support_suggestions",
    suggestions=[
        {"label": "Summarize", "prompt": "Summarize the current thread"},
        {"label": "Extract tasks", "prompt": "Extract all open tasks"},
    ],
    action="support.apply_suggestion",
)
```

## Runtime Updates

```python
return sdk.effects.respond(
    sdk.effects.ui_collection_append(
        "support_suggestions",
        "suggestions",
        {"label": "Draft release note", "prompt": "Draft the release note"},
    )
)
```
