# Agents

Agents are runtime assets that describe reusable AI behavior for a module.
They live under:

```text
modules/<module>/agents/
  __init__.py
  *.py
```

The module loader discovers and imports files in `agents/` during module
loading. The `@agent(...)` decorator registers each agent definition.

## What An Agent Defines

An agent definition can declare:

| Field | Purpose |
| --- | --- |
| `name` | Stable runtime name, module-qualified by the SDK. |
| `title` | Human-readable label. |
| `description` | Short explanation for discovery surfaces. |
| `objective` | Model objective, such as `chat`. |
| `system_prompt` | Model-facing behavior instructions. |
| `tools` | Tool names the agent is expected to use. |
| `skills` | Skill names loaded as instruction context. |
| `max_iterations` | Agent loop budget. |
| `mcp_servers` | Explicit MCP servers the agent can use. |
| `handler` | Whether the decorated function is the Python handler. |

Use agents for behavior that should be discoverable and reusable. If a feature
needs full control over persistence, streaming UI updates, or message windowing,
an action can still call a provider directly and pass registered tools, agents,
and skills in the provider options.

## Declarative Agent

A declarative agent registers metadata without a Python handler:

```python
from __future__ import annotations

from democrai.sdk.decorators import agent


@agent(
    "document-agent",
    title="Document agent",
    description="Answers focused questions about uploaded documents.",
    objective="chat",
    tools=[
        "chat.list-attachments",
        "chat.search-documents",
    ],
    skills=["chat.chat_context"],
    max_iterations=4,
    handler=False,
    system_prompt=(
        "Inspect attachments and retrieved document content before answering."
    ),
)
def document_agent():
    """Declarative agent metadata."""
```

Use this pattern when an action owns the orchestration but still wants the agent
contract to be registered and discoverable.

## Handler Agent

Use `handler=True` when the decorated function should be executed by the agent
runtime:

```python
from __future__ import annotations

from democrai.sdk.decorators import agent


@agent(
    "triage-agent",
    title="Triage agent",
    description="Classifies and summarizes incoming records.",
    objective="chat",
    tools=["reports.get-report"],
    max_iterations=3,
)
async def triage_agent(input: str = "", sdk=None, context: dict | None = None):
    report_id = context["report_id"]
    report = await sdk.ai.run_tool(
        "reports.get-report",
        arguments={"report_id": report_id},
        context=context,
    )
    return {
        "status": "ok",
        "content": f"Report status: {report['report']['status']}",
    }
```

Keep handler agents focused. If the implementation starts managing UI streams,
database writes, document ingestion, and provider options together, move that
orchestration into an action and let the agent definition describe the model
contract.

## Running Agents From SDK

Use `module_sdk.ai.run_agent(...)` when a module wants the runtime-managed agent
loop:

```python
result = await module_sdk.ai.run_agent(
    "reports.triage-agent",
    input="Summarize this report",
    context={"report_id": report.id},
    extra_tools=["reports.get-report"],
    extra_skills=["reports.report_context"],
    max_iterations=3,
)
```

The SDK also exposes discovery helpers:

```python
agents = module_sdk.ai.list_agents(module_name="reports")
agent = module_sdk.ai.get_agent("reports.triage-agent")
```

## Tools, Skills, And MCP

Declare the tools and skills an agent needs:

```python
@agent(
    "research-agent",
    tools=["reports.search-reports"],
    skills=["reports.research_context"],
    mcp_servers=["internal-docs"],
)
async def research_agent(...):
    ...
```

MCP servers must be listed explicitly. Do not use wildcards.

Tool and skill names should be stable module-qualified names. If an agent uses a
tool from another module, that dependency should be intentional and documented
in the feature design.

## Context And Message Windows

Agents should not assume the full application state is already in the prompt.
For chat-style features:

- send a bounded recent message window;
- include a compact summary when available;
- pass stable identifiers in `context`;
- expose retrieval and lookup through tools;
- keep long documents out of the prompt unless the user explicitly needs full
  content.

This keeps the provider request small while still giving the agent ways to ask
for the missing state.

## Runtime Events

When an action runs an agent, it can pass listener callbacks:

```python
async def on_message(event: dict):
    ...

result = await module_sdk.ai.run_agent(
    "reports.triage-agent",
    input="Review this report",
    context={"report_id": report.id},
    on_message=on_message,
)
```

Use runtime events for user-visible progress only when they help explain what
the agent is doing. Avoid appending every low-level event to the UI.

## Boundary Rules

Agents are contracts and orchestration units. They should not:

- import core agent runtime internals;
- reach into client renderers;
- read database tables outside the SDK boundary;
- load model providers directly;
- hide business persistence that belongs in actions or tools.

Use actions for user-triggered orchestration, tools for bounded capabilities,
and skills for reusable instructions.
