# Chat Module Tools

This step adds the tools used by the chat orchestrator.

The provider receives only a bounded message window. Tools let it inspect older
thread context, uploaded documents, extraction state, runtime statistics, and
the component surface without reaching into core internals.

Tool rules:

- use chat module models for chat-owned data;
- use SDK domains for media, knowledge, tasks, AI, and UI;
- scope every read through the current runtime context;
- return structured payloads with a `status` field;
- keep inputs explicit and small.

## Attachments

`chat.list-attachments` returns attachments for the current conversation plus
extraction status:

```python
@tool("list-attachments", title="List chat attachments", input_schema={...})
def list_attachments(*, sdk=None, context: dict | None = None) -> dict:
    conversation_id = int((context or {}).get("conversation_id") or 0)
    rows = Attachment.list(
        filters={"conversation_id": conversation_id},
        sort={"field": "id", "direction": "asc"},
        page=0,
        page_size=200,
    )["rows"]
    statuses = sdk.knowledge.list_extraction_statuses(
        [row["extraction_request_id"] for row in rows if row["extraction_request_id"]]
    )
    ...
```

The returned payload includes all attachments and a `documents` subset for
non-image/audio/video files with an extraction request id.

## Reading Documents

The current analysis tool is `chat.read-document`.

It resolves a request id from either `attachment_id` or
`extraction_request_id`, checks that it belongs to the current conversation, and
calls:

```python
module_sdk.knowledge.read_document_blocks(
    request_id=request_id,
    max_chars=budget,
    blocks=resolved_blocks,
    kind=kind,
)
```

Without `blocks`, the result returns the whole document when it fits the budget
or an index of available blocks. With `blocks`, it returns those block ordinals
up to the budget. `kind` selects `chunk`, `table`, `formula`, or `image`.

`chat.get-document-markdown` still exists as a compatibility/simple full
markdown helper, but the tutorial flow should prefer `chat.read-document`
because it supports bounded block access and counts.

## Full Document Summary

`chat.extract-full-summary` builds and caches a document map for large uploads.

The tool:

1. resolves the extraction request for the current conversation;
2. checks `module_sdk.knowledge.list_items_for_summary(...)` for a cached
   document summary;
3. reads the extracted markdown when no cache exists;
4. splits it into budgeted sections;
5. summarizes sections with the current chat model;
6. stores the final document map with
   `module_sdk.knowledge.store_item_summary(...)`.

The cached summary is returned on later calls. This gives the agent an overview
before it asks for specific blocks through `chat.read-document`.

## Document Search

`chat.search-documents` first uses knowledge retrieval when knowledge is
enabled:

```python
result = await module_sdk.knowledge.retrieve(
    query_text=query,
    top_k=top_k,
    metadata_filters={
        "module_name": "chat",
        "conversation_id": conversation_id,
    },
)
```

If knowledge is disabled or returns no matches, the tool falls back to
`module_sdk.knowledge.search_extracted_items(...)` over extraction request ids
linked to the current conversation.

This is the important distinction: retrieval is preferred when embeddings are
available, but extracted markdown remains useful even without vector search.

## Message Search

`chat.search-messages` searches older persisted thread messages.

When knowledge is enabled, it uses `module_sdk.knowledge.retrieve(...)` with the
same `module_name=chat` and `conversation_id` metadata filter. Otherwise it
falls back to the module model filter `content_query`.

The tool does not load the whole thread into Python.

## Wait Tool

`chat.wait-seconds` is a bounded async sleep. The system prompt tells the model
to use it only when extraction is pending and the uploaded file is needed.

The input is a number of seconds with a small maximum. It exists to handle the
normal race between upload and background extraction.

## Runtime Stats

`chat.runtime-stats` returns compact facts for the active conversation:

- message count;
- attachment count;
- persisted component count;
- visible/running background tasks;
- knowledge runtime configuration.

It uses `module_sdk.tasks.list_user_tasks(...)` and chat models. The tool does
not render UI. The component agent owns visual display.

## Component Tools

The chat module persists A2UI output through dedicated `chat.show-*` tools. The
model does not send raw A2UI envelopes.

`chat.show-component` is informational; it lists available component tools. It
does not persist anything.

Specialized tools accept flat inputs and build validated A2UI payloads in
Python. Examples:

| Tool | Input | Output |
| --- | --- | --- |
| `chat.show-alert` | `title`, `text`, `variant` | `Alert` |
| `chat.show-badge` | `text`, `variant` | `Badge` |
| `chat.show-card` | `title`, `body`, `variant` | `Card` with `Title`/`Markdown` |
| `chat.show-chart` | `chart_type`, `labels`, `data`, `title` | compact `Chart` in a bounded card |
| `chat.show-table` | `columns`, `rows` | `DataTable` |
| `chat.show-metric-grid` | metric label/value pairs | `Grid` of metric cards |
| `chat.show-tabs` | text tabs | `Tabs` with generated matching child ids |
| `chat.show-sequence-diagram` | participants and messages | `SequenceDiagram` |

Every persisted component becomes a `ChatComponent` row. The submit action sees
the tool response through `on_message`, converts that row into a
`kind: component` message, and appends it to `MessageList`.

That order keeps UI generation deterministic:

1. tool validates and persists component payload;
2. action appends the persisted component message;
3. assistant final text can say what was displayed without embedding raw JSON.
