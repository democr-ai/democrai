# AI Chat

[<- Back to Components Index](../index.md)

## Purpose

Chat interface composition for thread history, message timelines, chat toolbar actions, suggestions, composer input, and attachment payloads.

## Recommended Layout

```text
Row or layout shell
├── ThreadList          # optional sidebar
└── Column
    ├── Row             # chat toolbar, optional
    ├── ScrollArea
    │   └── MessageList
    ├── Suggestions     # optional
    └── Composer
```

## What To Read

- [Threads](./threads.md)
- [Messages And Runtime Updates](./messages-and-runtime-updates.md)
- [Composer](./composer.md)
- [Suggestions](./suggestions.md)

## Guidelines

- Prefer `MessageList` over `MessageItem` for real chat UIs.
- Prefer stable message `id` values so runtime patches can target messages safely.
- Prefer `kind: component` with `content.components` when the assistant must add charts, cards, tables, or follow-up UI to the timeline.
- Put chat toolbar controls outside the `ScrollArea`. The toolbar is just normal YAML composition; each button decides what action payload it emits.
- Treat attachment clicks as application actions. The framework passes the attachment payload; the module decides what to do with it.
- Keep persisted chat data backend-owned. Use runtime patches for the visible window, not as the primary database model.
- Prefer one rooted YAML page tree. Do not document AI page examples as multiple root nodes.

## YAML Example

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
            context: {command: download, target: support_messages}
    - kind: ScrollArea
      id: support_messages_scroll
      scroll_y: true
      scroll_x: false
      children:
        - kind: MessageList
          id: support_messages
          messages:
            - id: m_1
              role: user
              kind: text
              content: {text: Summarize the release risks.}
              meta: user · 11:02
            - id: m_2
              role: assistant
              kind: text
              content: {text: The main risks are UI regressions and incomplete test coverage.}
              meta: assistant · 11:03
          on_load_more:
            name: support.load_older_messages
            context: {target: support_messages}
    - kind: Composer
      id: support_composer
      placeholder: Write a message...
      send_action:
        name: support.send_message
        context: {}
      cancel_action:
        name: support.stop_generation
        context: {}
```
