# Chat Module Orchestration

This step connects a persisted user turn to the AI runtime.

The chat action resolves a chat provider through `module_sdk.ai`, then calls
`provider.generate_stream(...)` directly. This is deliberate: the chat page must
stream assistant text, publish step rows, persist component messages, ingest
outputs into knowledge, and keep the visible timeline stable.

## Runtime Assets

The current orchestration declares:

```python
RECENT_MESSAGE_LIMIT = 10

CHAT_TOOLS = [
    "chat.search-messages",
    "core.ask-user",
    "chat.list-attachments",
    "chat.read-document",
    "chat.extract-full-summary",
    "chat.search-documents",
    "chat.search-messages",
    "chat.wait-seconds",
]

CHAT_SKILLS = ["chat.chat_context"]

CHAT_AGENTS = [
    "chat.stats-agent",
    "chat.component-agent",
]
```

The main request acts as the conversation router. It can answer directly, call
direct tools for documents and older messages, call `core.ask-user` for
structured user input, or delegate focused work to the stats/component agents.

There is no `chat.document-agent` in the current module. Document work is done
through direct chat tools.

## Provider Messages

`build_provider_messages(...)` sends a bounded conversation window:

- one system message with routing instructions;
- the persisted thread summary when present;
- the last `RECENT_MESSAGE_LIMIT` non-task messages;
- attachment status overview for current thread attachments;
- direct image attachments when the provider can receive them.

Task messages are skipped because they are UI state. Older chat context is
available through `chat.search-messages`. Uploaded document content is available
through `chat.list-attachments`, `chat.search-documents`, `chat.read-document`,
and `chat.extract-full-summary`.

The system prompt also tells the model:

- use `chat.extract-full-summary` for large document overviews;
- use `chat.read-document` with `kind=chunk/table/formula/image` for precise
  document blocks;
- use `chat.wait-seconds` once when extraction is pending and the file is needed;
- use the stats agent before visual summaries;
- use the component agent for rendered UI and never emit raw A2UI JSON;
- use `core.ask-user` with a flat Form model when a value must come from the user.

## Provider Options

Composer option entries become provider options:

```python
def build_provider_options(payload: dict) -> dict:
    return {
        **_options(list(payload.get("options") or [])),
        "tools": [*CHAT_TOOLS, *_selected_names(payload, "selected_tools")],
        "skills": [*CHAT_SKILLS, *_selected_names(payload, "selected_skills")],
        "agents": [*CHAT_AGENTS, *_selected_names(payload, "selected_agents")],
        "mcp": _selected_names(payload, "selected_mcp"),
        "tool_max_iterations": 10,
    }
```

Option keys prefixed with `extra.` are converted into nested provider options.
The composer UI receives available options from
`module_sdk.ai.get_composer_options_for_capability("chat")`; the module does
not invent model-specific option schemas.

## Runtime Events

The provider can call `on_message`. The chat module filters important events
into one transient status row:

- tool call/response/failure;
- agent call/response/failure;
- agent pipeline start/finish;
- MCP call/response.

Successful chat component tool responses are also inspected. If a response came
from a known `chat.show-*` component tool, the action persists a `ChatComponent`
row and appends a `kind: component` message to the timeline.

## Streaming

`run_chat_orchestration(...)` resolves the provider, builds messages/options,
and streams chunks:

```python
provider_result = await module_sdk.ai.get_provider_for_objective(
    "chat",
    required_capabilities=["chat"],
)
provider = provider_result["provider"]

async for chunk in provider.generate_stream(
    messages=build_provider_messages(module_sdk, conversation),
    options=build_provider_options(payload),
    request_id=request_id,
    ingest=knowledge_state(module_sdk)["enabled"],
    ingest_meta={
        "module_name": "chat",
        "conversation_id": int(conversation.id),
        "thread_id": int(conversation.id),
        "message_id": int(user_message.id),
    },
    on_message=_on_message,
):
    ...
```

Text and reasoning are accumulated separately. The action receives deltas and
updates one temporary assistant row. When the final assistant message is
persisted, the temporary row is replaced with the database-backed row.

`ingest_meta` scopes generated content for later knowledge retrieval.

## Summary Refresh

Every completed turn can refresh the thread summary. The module collects
messages after `summary_until_sequence`; when enough new messages exist it calls
`module_sdk.ai.run_agent("chat.summary-agent", ...)`, stores the compact
summary, and advances `summary_until_sequence`.

The summary is then included in future provider messages so the direct context
window can remain small.
