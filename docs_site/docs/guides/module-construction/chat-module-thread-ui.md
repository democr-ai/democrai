# Chat Module Thread UI

This step creates `/chat/thread/<id>`, the persistent conversation page.

It reuses the same shell shape as the home page, but binds composer state to
`/chat/thread`, highlights the active thread, loads the latest timeline window,
and wires the composer to `chat.submit_message`.

## Thread YAML

Create `modules/chat/utils/ui/yaml/thread.yaml`.

The thread layout mirrors `index.yaml`. The differences are the active thread
binding and thread-specific composer store paths:

```yaml
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
      action:
        name: open_drawer
        context:
          type: nav
          path: /chat/thread/$item.id/rename
    - label: "@t/chat.thread.delete"
      action:
        name: chat.delete_thread
        context:
          item_id: $item.id
      confirm:
        text: "@t/chat.thread.delete.confirm.text"
        confirm_text: "@t/chat.thread.delete.confirm.accept"
        cancel_text: "@t/chat.thread.delete.confirm.cancel"
```

```yaml
- kind: Composer
  id: chat_composer
  disabled: "@state/page/chat/thread/composer_disabled"
  enable_attachment: "@state/page/chat/thread/attachment_enabled"
  attachment_accept: "@state/page/chat/thread/attachment_accept"
  model_capabilities: "@state/page/chat/thread/model_capabilities"
  options: "@state/page/chat/thread/options"
  options_schema: "@state/page/chat/thread/options_schema"
  options_editable: "@state/page/chat/thread/options_editable"
  send_action:
    name: chat.submit_message
    context:
      source: chat_thread
      composer: chat_composer
      target: chat_message_list
  cancel_action:
    name: chat.stop_generation
    context:
      source: chat_thread
      composer: chat_composer
```

The `MessageList` declares `on_load_more` in YAML, but the page render replaces
its context with the current `conversation_id` and oldest visible sequence.

## Timeline State

The timeline is composed from two tables:

- `Message` rows for user, assistant, and task messages;
- `ChatComponent` rows for persisted A2UI component output.

Both use `sequence`, so the helper queries each table newest-first, merges the
window, then returns rows oldest-first for rendering.

```python
THREAD_MESSAGE_PAGE_SIZE = 30

def thread_messages(module_sdk, conversation_id: int) -> list[dict]:
    return [item[1] for item in _timeline_window(module_sdk, conversation_id)]

def thread_messages_before(module_sdk, conversation_id: int, before_sequence: int) -> list[dict]:
    return [
        item[1]
        for item in _timeline_window(
            module_sdk,
            conversation_id,
            before_sequence=before_sequence,
            page_size=THREAD_MESSAGE_PAGE_SIZE,
        )
    ]
```

Message rows include attachments in `content.attachments`. Component rows use:

```python
{
    "id": f"component_{row['id']}",
    "role": "assistant",
    "kind": "component",
    "status": "completed",
    "content": {"components": row["payload"]["components"]},
}
```

## Render The Thread Page

Create `modules/chat/ui/thread/[id].py`:

```python
@permission_required(["chat.view"])
async def render(params: dict, session: dict):
    conversation_id = int(params["route_params"]["id"])
    conversation = sdk.database.get(Conversation, str(conversation_id))
    if conversation is None:
        return sdk.ui.load("utils/ui/yaml/index")

    builder = sdk.ui.load("utils/ui/yaml/thread")
    llm = await chat_llm_state(sdk)
    llm_ready = bool(llm.get("configured"))
    accept = attachment_accept(sdk)
    initial_messages = thread_messages(sdk, conversation_id)
    oldest = visible_oldest_sequence(sdk, initial_messages)

    builder.set_data(
        "/chat/thread_list",
        thread_list_state(sdk, active_thread_id=conversation_id),
    )
    builder.get_component("chat_message_list").set_property("messages", initial_messages)
    builder.get_component("chat_composer").set_property("voice", stt_configured(sdk))
    builder.get_component("chat_composer").set_property(
        "send_action",
        {
            "name": "chat.submit_message",
            "context": {
                "source": "chat_thread",
                "conversation_id": str(conversation_id),
                "composer": "chat_composer",
                "target": "chat_message_list",
            },
        },
    )
    builder.get_component("chat_message_list").set_property(
        "on_load_more",
        {
            "name": "chat.load_older_messages",
            "context": {
                "target": "chat_message_list",
                "conversation_id": str(conversation_id),
                "before_sequence": oldest,
            },
        },
    )
    builder.set_store("/chat/current/oldest_sequence", oldest, scope="page")
    builder.set_store("/chat/current/attachments", thread_attachments(sdk, conversation_id), scope="page")
    builder.set_store("/chat/current/knowledge", knowledge_state(sdk), scope="page")
    builder.set_store(
        "/chat/thread",
        {
            "conversation_id": str(conversation_id),
            "title": str(conversation.title or ""),
            "composer_disabled": not llm_ready,
            "llm_status": str(llm.get("status") or ""),
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

The runtime property updates are intentional here:

- `messages` is a large dynamic collection and should not be rebound on every
  streaming update;
- `send_action` and `on_load_more` need the route `conversation_id`;
- `voice` depends on runtime STT state.

## Rename Drawer

Create `modules/chat/utils/ui/yaml/thread_rename.yaml` with a small `Form`
bound to `/chat/thread_rename/values`. The route
`/chat/thread/<id>/rename` loads it in a drawer and sets form action context:

```python
builder.set_data(
    "/chat/thread_rename",
    {
        "conversation_id": str(conversation_id),
        "values": {"title": str(conversation.title or "")},
    },
)
```

The form submits `chat.rename_thread`, then the action closes the drawer and
refreshes the sidebar data.

## Load Older Messages

`chat.load_older_messages` reads `/chat/current/oldest_sequence` from the client
store with `module_sdk.effects.ask_current_store_value(...)`, fetches the next
window, prepends it to `chat_message_list.messages`, and updates the oldest
sequence store.

This avoids full page rerenders and keeps scroll behavior stable in web and
desktop clients.
