# Tools

Tools are callable runtime capabilities exposed to agents and AI orchestration.
They live under:

```text
modules/<module>/tools/
  __init__.py
  *.py
```

The module loader discovers and imports files in `tools/` during module loading.
The `@tool(...)` decorator registers each callable in the agent tool registry.

## When To Create A Tool

Create a tool when the model needs a bounded capability:

- read one slice of module state;
- check the status of a background process;
- retrieve document content;
- compute statistics;
- persist a structured artifact requested by the model;
- call an approved SDK service.

Do not turn every helper into a tool. A tool is a public runtime contract for an
agent. It needs a stable name, description, input schema, and structured return
shape.

## Minimal Tool

Create `modules/<module>/tools/records.py`:

```python
from __future__ import annotations

from democrai.sdk.decorators import tool

from modules.reports.models import Report


@tool(
    "get-report",
    title="Get report",
    description="Load one report owned by the reports module.",
    input_schema={
        "type": "object",
        "properties": {
            "report_id": {"type": "integer"},
        },
        "required": ["report_id"],
    },
)
async def get_report(report_id: int, *, sdk, context: dict | None = None):
    row = Report.get(report_id)
    if row is None:
        return {"status": "error", "error": "not_found"}

    return {
        "status": "ok",
        "report": {
            "id": row.id,
            "title": row.title,
            "status": row.status,
        },
    }
```

The SDK qualifies the tool name with the module name. In module `reports`,
`get-report` is registered as `reports.get-report`.

## Input Schema

Always provide an input schema for agent-facing tools:

```python
input_schema={
    "type": "object",
    "properties": {
        "query": {"type": "string"},
        "limit": {"type": "integer", "minimum": 1, "maximum": 20},
    },
    "required": ["query"],
}
```

The schema is part of the model contract. Keep it narrow and domain-specific.
Avoid catch-all payloads unless the tool genuinely accepts arbitrary structured
data.

## Return Shape

Prefer a structured payload with `status`:

```python
return {
    "status": "ok",
    "matches": rows,
}
```

For expected failures, return an error payload instead of raising:

```python
return {
    "status": "error",
    "error": "query_required",
}
```

Raise only for programmer errors or platform failures that the action/runtime
should surface as execution errors.

## Context

Tools can receive runtime context:

```python
async def search_reports(query: str, *, sdk, context: dict | None = None):
    conversation_id = context["conversation_id"]
    ...
```

Use context for identifiers the orchestration already knows, such as
`conversation_id`, `message_id`, `thread_id`, or module-specific scope. Do not
ask the model to invent identifiers that the action can pass reliably.

## Tool Options

The decorator supports:

| Option | Purpose |
| --- | --- |
| `title` | Human-readable label for tool lists. |
| `description` | Model-facing explanation of what the tool does. |
| `input_schema` | JSON schema for arguments. |
| `confirmation_required` | Marks tools that should require approval before execution. |
| `access` | Access policy rules for external resources. |
| `user_selectable` | Whether the tool appears in user-selectable tool lists. |

Use `user_selectable=False` for internal tools that should be available to a
specific agent but not shown as a general composer option.

## Tool Discovery From SDK

Module code can inspect registered tools through the SDK:

```python
tools = module_sdk.ai.list_tools(module_name="reports")
tool = module_sdk.ai.get_tool("reports.get-report")
```

`list_tools(...)` returns user-selectable tools by default. Pass
`user_selectable_only=False` when the caller must inspect internal tools too.

## Boundary Rules

Tools run in the module context and should use the same boundaries as actions:

- use module models for module-owned tables;
- use `sdk.models` for core-managed entities exposed by the SDK;
- use SDK domains for media, knowledge, tasks, AI, system state, and events;
- never import core services or client renderer code;
- never read another module's tables directly.

For document-aware tools, keep ingestion and retrieval separate:

- use attachment rows to know what was uploaded;
- use knowledge/extraction SDK methods for extraction state and extracted
  markdown;
- use retrieval only when the knowledge service is active and configured;
- return a clear `status` when a document is still pending.

## Bounded Work

Tools should finish quickly. If a tool waits, make the wait bounded:

```python
@tool(
    "wait-seconds",
    title="Wait seconds",
    description="Wait briefly for an asynchronous resource to become available.",
    input_schema={
        "type": "object",
        "properties": {
            "seconds": {"type": "number", "minimum": 0, "maximum": 10},
        },
        "required": ["seconds"],
    },
)
async def wait_seconds(seconds: float):
    await asyncio.sleep(seconds)
    return {"status": "ok", "waited": seconds}
```

Do not create tools that block indefinitely. The agent runtime must be able to
continue, retry, or answer with a clear limitation.
