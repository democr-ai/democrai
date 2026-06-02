# Chat Module Actions

This step adds the runtime behavior behind the chat UI.

The module has two submit paths:

- `chat.start_thread` runs from `/chat/index`, creates a conversation, starts
  the first turn, then navigates to `/chat/thread/<id>`;
- `chat.submit_message` runs inside an existing thread and patches the current
  `MessageList` incrementally.

Both paths share the same persistence helper.

## User Turn Persistence

`create_user_turn(module_sdk, ctx)` reads the composer payload from
`ctx["chat_composer"]`, creates the conversation when needed, persists the user
message, creates attachment rows, and creates task messages for uploads that
started background extraction.

The helper returns:

```python
{
    "conversation": conversation,
    "message": message,
    "attachments": attachments,
    "task_messages": task_messages,
    "created": created,
}
```

Important details:

- empty text with no attachments raises `ValueError("chat_message_empty")`;
- attachments keep `storage_path`, `file_id`, `extraction_request_id`, and
  `background_task_id`;
- `last_message_at` is updated on the conversation;
- a new untitled thread receives `@t/chat.thread.untitled`.

Messages and component messages share one `sequence`, so `next_sequence(...)`
checks both `Message` and `ChatComponent`.

## Stream Helpers

The thread action publishes directly to the current stream:

```python
await module_sdk.effects.publish_collection_append(
    stream_id,
    "chat_message_list",
    "messages",
    row,
)
```

The same collection is updated with:

- `publish_collection_append(...)` for user, task, component, and first stream rows;
- `publish_collection_replace(...)` for agent status and streaming assistant text;
- `publish_collection_remove(...)` for transient status rows;
- `publish_property_update(..., "scroll", "bottom")` to keep the timeline pinned;
- `publish_property_update(..., "current_request", request_id)` so the composer
  can cancel the current provider request.

The returned action response stays small because most UI changes have already
been published to the stream.

## Submit Existing Thread

`chat.submit_message` requires a `conversation_id`. It publishes an error toast
when the context is missing.

The successful flow is:

1. call `create_user_turn(...)`;
2. append the user row and any background task rows;
3. set `chat_composer.current_request` and clear composer value;
4. append one transient agent status row;
5. call `run_chat_orchestration(...)`;
6. replace the streaming assistant row with the persisted assistant message;
7. remove the transient status row;
8. refresh the sidebar page data and active row.

The action passes callbacks into orchestration:

- `on_step(row)` replaces the status row with the latest important runtime step;
- `on_message(event)` persists successful A2UI component tool responses as
  `ChatComponent` rows and appends component messages;
- `on_stream_delta(text, reasoning)` creates or replaces the temporary assistant
  streaming row.

## Start First Thread

`chat.start_thread` reuses the same submit helper, then navigates:

```python
@action("start_thread")
@permission_required(["chat.write"])
async def start_thread(ctx: dict, session: dict, module_sdk):
    effects, conversation = await _submit_thread_message(ctx, module_sdk)
    return module_sdk.effects.respond(
        module_sdk.effects.navigate(f"/chat/thread/{conversation.id}", render=True)
    )
```

The first turn can stream into the home page briefly, but the final visible
state is the newly created thread route.

## Stop Generation

`chat.stop_generation` reads the current request id from `ctx["chat_composer"]`
and calls the AI runtime cancellation API:

```python
request_id = (ctx.get("chat_composer") or {}).get("current_request")
if request_id:
    module_sdk.ai.cancel_request(request_id)
    await module_sdk.effects.publish_property_update(
        ctx.get("stream_id"),
        "chat_composer",
        "current_request",
        "",
    )
```

It does not delete messages. The running submit action receives cancellation
and updates the transient status row.

## Navigation And Sidebar Actions

The current action set includes:

| Action | Purpose |
| --- | --- |
| `chat.open_thread` | Navigate to `/chat/thread/<item_id>`. Accepts `item_id` and legacy `threadId`. |
| `chat.new_thread` | Navigate to `/chat`. |
| `chat.thread_page_prev` | Ask the client for current sidebar page and publish previous page data. |
| `chat.thread_page_next` | Ask the client for current sidebar page and publish next page data. |
| `chat.rename_thread` | Update title, close drawer, refresh sidebar, show toast. |
| `chat.delete_thread` | Delete knowledge metadata, media, attachments, components, messages, and conversation. |
| `chat.load_older_messages` | Prepend an older timeline window and update `/chat/current/oldest_sequence`. |

Pagination and rename use `module_sdk.effects.ask_current_data_value(...)` to
read current sidebar state from the client. That keeps drawer and main-content
updates pointed at the correct surface.

Deletion cleans both module-owned data and SDK-owned projections:

```python
module_sdk.knowledge.delete_by_metadata({"conversation_id": conversation_id}, force=True)
module_sdk.media.delete(storage_path)
module_sdk.database.delete(Conversation, conversation_id)
```

Do not delete knowledge repository rows directly from the module.
