# Chat Module Home UI

This step creates `/chat/index`: the shell shown before a conversation exists.
It renders the sidebar, an empty message list, and a composer wired to
`chat.start_thread`.

The page is YAML-first. Python loads the YAML, computes small state objects, and
seeds data/store values. It does not build the layout in Python.

## YAML Layout

Create `modules/chat/utils/ui/yaml/index.yaml`.

The current chat shell uses `Splitter`, a `List` bound to
`/chat/thread_list/items`, sidebar pagination, and a `Composer` whose options
come from page store:

```yaml
- kind: Splitter
  id: chat_thread_page
  stretch: true
  sizes: [250, 900]
  max_sizes: [250, 0]
  children:
    - kind: Sidebar
      id: chat_sidebar
      padding: [16, 16, 16, 16]
      children:
        - kind: Row
          id: chat_sidebar_header
          children:
            - kind: Title
              id: chat_sidebar_title
              text: "@t/chat.sidebar.title"
              level: 3
              stretch: true
            - kind: Button
              id: chat_new_thread
              label: "@t/chat.sidebar.new"
              icon: ric.add-line
              action:
                name: chat.new_thread
        - kind: ScrollArea
          id: chat_thread_scroll
          stretch: true
          children:
            - kind: List
              id: chat_thread_list
              template: text
              data_source:
                type: binding
                data:
                  path: /chat/thread_list/items
              on_item_click:
                name: chat.open_thread
                context:
                  item_id: $item.id
              item_actions:
                - label: "@t/chat.thread.rename"
                  icon: ric.edit-line
                  action:
                    name: open_drawer
                    context:
                      type: nav
                      path: /chat/thread/$item.id/rename
                - label: "@t/chat.thread.delete"
                  icon: ric.delete-bin-6-line
                  variant: danger
                  action:
                    name: chat.delete_thread
                    context:
                      item_id: $item.id
                    confirm:
                      text: "@t/chat.thread.delete.confirm.text"
                      confirm_text: "@t/chat.thread.delete.confirm.accept"
                      cancel_text: "@t/chat.thread.delete.confirm.cancel"
              capabilities:
                - dataSource.set
                - dataSource.data.replace
                - dataSource.data.remove
        - kind: Row
          id: chat_thread_pagination
          children:
            - kind: Button
              id: chat_thread_prev
              label: "@t/chat.sidebar.prev"
              action:
                name: chat.thread_page_prev
            - kind: Text
              id: chat_thread_page_label
              text: "@data/chat/thread_list/page_label"
              stretch: true
            - kind: Button
              id: chat_thread_next
              label: "@t/chat.sidebar.next"
              action:
                name: chat.thread_page_next
    - kind: ContentArea
      id: chat_content
      stretch: true
      children:
        - kind: Column
          id: chat_thread_conversation
          stretch: true
          children:
            - kind: ScrollArea
              id: chat_messages_scroll
              stretch: true
              children:
                - kind: MessageList
                  id: chat_message_list
                  messages: []
                  on_attachment_click:
                    name: chat.open_attachment_preview
                    context:
                      source: chat_message_list
                  capabilities:
                    - messages.append
                    - messages.prepend
                    - messages.replace
                    - messages.set
                    - scroll.set
            - kind: Composer
              id: chat_composer
              placeholder: "@t/chat.composer.placeholder"
              disabled: "@state/page/chat/home/composer_disabled"
              enable_attachment: "@state/page/chat/home/attachment_enabled"
              attachment_multiple: true
              attachment_accept: "@state/page/chat/home/attachment_accept"
              ingest: true
              voice_action:
                name: composer_transcribe_audio
              model_capabilities: "@state/page/chat/home/model_capabilities"
              options: "@state/page/chat/home/options"
              options_schema: "@state/page/chat/home/options_schema"
              options_editable: "@state/page/chat/home/options_editable"
              send_action:
                name: chat.start_thread
                context:
                  source: chat_thread
                  composer: chat_composer
                  target: chat_message_list
              cancel_action:
                name: chat.stop_generation
                context:
                  source: chat_thread
                  composer: chat_composer
              capabilities:
                - value.set
                - disabled.set
                - current_request.set
```

The important contracts are:

- the thread sidebar is a generic `List`, not a chat-specific `ThreadList`;
- thread rows come from `/chat/thread_list/items`;
- rename opens a drawer through `open_drawer`;
- delete calls `chat.delete_thread` with `item_id`;
- the composer submits the first message through `chat.start_thread`;
- uploads use `ingest: true`, so extraction requests can be linked to messages.

## UI State Helpers

The render function relies on small projection helpers:

```python
def attachment_accept(module_sdk) -> str:
    return ",".join(sorted(module_sdk.extractors.list_ingestible_mime_types()))
```

`thread_list_state(...)` returns the full sidebar data model:

```python
{
    "items": [...],
    "page": 0,
    "page_size": 15,
    "total_rows": 42,
    "has_prev": False,
    "has_next": True,
    "page_label": "1/3",
    "active_thread_id": "",
}
```

Each row contains at least `id`, `title`, `text`, `snippet`, `preview`, and
`path`.

`knowledge_state(module_sdk)` reads `module_sdk.knowledge.get_runtime_config()`
and returns whether embedding retrieval is available. The module does not reach
into knowledge internals.

`chat_llm_state(module_sdk)` delegates composer option discovery to
`module_sdk.ai.get_composer_options_for_capability("chat")`.

## Render The Home Page

Create `modules/chat/ui/index.py`:

```python
@permission_required(["chat.view"])
async def render(params: dict, session: dict):
    builder = sdk.ui.load("utils/ui/yaml/index")

    llm = await chat_llm_state(sdk)
    llm_ready = bool(llm.get("configured"))
    accept = attachment_accept(sdk)

    builder.set_data("/chat/thread_list", thread_list_state(sdk))
    builder.get_component("chat_message_list").set_property("messages", [])
    builder.get_component("chat_composer").set_property("voice", stt_configured(sdk))

    builder.set_store("/chat/current/attachments", [], scope="page")
    builder.set_store("/chat/current/knowledge", knowledge_state(sdk), scope="page")
    builder.set_store(
        "/chat/home",
        {
            "llm_ready": llm_ready,
            "llm_status": str(llm.get("status") or ""),
            "composer_disabled": not llm_ready,
            "attachment_accept": accept,
            "attachment_enabled": bool(accept),
            "model_capabilities": list(llm.get("model_capabilities") or []),
            "options": dict(llm.get("options") or {}),
            "options_schema": dict(llm.get("options_schema") or {"fields": []}),
            "options_editable": bool(llm.get("options_editable")),
        },
        scope="page",
    )
    return builder
```

The explicit `set_property(...)` calls are narrow runtime exceptions:

- `MessageList.messages` is seeded once and then patched incrementally;
- `Composer.voice` depends on runtime STT availability.

Layout, bindings, actions, labels, and component structure remain in YAML.
