# AI Threads

[<- Back to AI Chat](./index.md)

This page covers the structural conversation components:

- `Thread`
- `ThreadList`

## Build Pattern

For application chat pages, prefer an explicit layout shell: a sidebar with `ThreadList`, then a chat column with toolbar, scrollable `MessageList`, suggestions, and composer. Use `Thread` only when you specifically want its container behavior; do not rely on it for chat scrolling.

YAML example with a single rooted page tree:

```yaml
- kind: Row
  id: support_chat_shell
  children:
    - kind: ThreadList
      id: support_thread_list
      threads:
        - id: t_1
          title: Release planning
          snippet: Risk summary
          preview: Risk summary
        - id: t_2
          title: Sprint review
          snippet: Open actions
          preview: Open actions
      active_thread_id: t_1
      action:
        name: support.open_thread
        context: {}
    - kind: Column
      id: support_chat_column
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
                context: {command: download, target: support_messages}
        - kind: ScrollArea
          id: support_messages_scroll
          scroll_y: true
          children:
            - kind: MessageList
              id: support_messages
              messages: []
        - kind: Composer
          id: support_composer
          placeholder: Write a message...
          send_action:
            name: support.send_message
            context: {}
```

## Thread Parameters

| Property | Web | Desktop | Runtime update | Notes |
|---|---|---|---|---|
| `id` | yes | yes | no | Required |
| `children` | yes | yes | yes | Standard container composition |
| `auto_scroll` | partial | partial | avoid relying on it | `MessageList` is the reliable scroll actor |
| `style` | yes | yes | yes | Standard component styling |

`auto_scroll` should not be the core scrolling strategy for chat UIs. The reliable scrolling and history-loading behavior lives in `MessageList`.

## ThreadList Parameters

| Property | Web | Desktop | Runtime update | Notes |
|---|---|---|---|---|
| `id` | yes | yes | no | Required |
| `threads` | yes | yes | yes | `append`, `remove`, `replace`, `set` supported |
| `active_thread_id` | yes | yes | yes | Current thread selection |
| `action` | yes | yes | render-time | Fired on click |
| `style` | yes | yes | yes | Standard styling |

For cross-renderer compatibility, populate both `snippet` and `preview` when you have a short thread summary.

## Runtime Updates

Set the active thread:

```python
return sdk.effects.respond(
    sdk.effects.ui_property_update("support_thread_list", "active_thread_id", "t_2")
)
```

Append a new thread:

```python
return sdk.effects.respond(
    sdk.effects.ui_collection_append(
        "support_thread_list",
        "threads",
        {
            "id": "t_3",
            "title": "Launch prep",
            "snippet": "Checklist review",
            "preview": "Checklist review",
        },
    )
)
```
