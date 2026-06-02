# Chat Module Agents And Skills

This step registers the chat module's agent assets and reusable skill.

The main chat request is not a registered general-purpose agent. It is the
action-owned `provider.generate_stream(...)` flow. Registered agents are focused
runtime assets the main request can call.

## Stats Agent

`modules/chat/agents/stats.py` registers `chat.stats-agent`.

It has one tool:

```python
tools=["chat.runtime-stats"]
```

The prompt tells it to return compact structured facts from the stats tool only.
It does not render UI components and does not invent missing metrics.

Use this agent when the user asks for counts, monitoring, task state, or current
conversation/runtime statistics.

## Component Agent

`modules/chat/agents/component.py` registers `chat.component-agent`.

It owns visual output and can call the dedicated component tools:

```python
tools=[
    "chat.show-alert",
    "chat.show-badge",
    "chat.show-chart",
    "chat.show-table",
    "chat.show-list",
    "chat.show-card",
    "chat.show-collapse",
    "chat.show-metric-grid",
    "chat.show-descriptions",
    "chat.show-markdown",
    "chat.show-progress",
    "chat.show-sequence-diagram",
    "chat.show-tabs",
    "chat.show-text",
    "chat.show-title",
    "chat.show-component",
]
```

The agent receives compact data from the main request. It should not retrieve
documents or older messages. It should not emit raw A2UI JSON. It calls one or
more flat, dedicated component tools.

## Title Agent

`chat.title-agent` is registered as a narrow title-generation asset:

```python
@agent("title-agent", objective="chat", max_iterations=1, handler=False)
def title_agent():
    ...
```

The current action path does not require this agent for every new thread; the
submit flow can derive a short placeholder title from the first user message.
Keep the agent documented as an available asset, not as a mandatory runtime step.

## Summary Agent

`chat.summary-agent` maintains compact thread summaries.

After enough new messages have accumulated, the conversation action calls:

```python
await module_sdk.ai.run_agent(
    "chat.summary-agent",
    input=prompt,
    context={
        "source": "chat.thread.summary",
        "conversation_id": int(conversation.id),
        "summary_until_sequence": since_sequence,
    },
    max_iterations=2,
)
```

The resulting summary is stored on `Conversation.summary`, and
`summary_until_sequence` advances. Future provider calls include that summary
before the recent message window.

## Chat Context Skill

Create `modules/chat/skills/chat_context/SKILL.md`:

```markdown
---
name: chat_context
title: Chat Context
description: Operational guidance for the Democrai chat module.
summary: Use direct chat tools for messages and delegate focused stats or component work to dedicated agents.
tags:
  - chat
  - documents
  - messages
allowed_tools:
  - chat.search-messages
  - core.ask-user
  - chat.list-attachments
  - chat.search-documents
  - chat.get-document-markdown
  - chat.wait-seconds
  - agent.chat.stats-agent
  - agent.chat.component-agent
---

# Chat Context

The main chat request is the conversation router. It sees recent messages and
the thread summary, uses direct tools for document retrieval, and delegates
focused statistics or component work to subagents.

Use `chat.list-attachments` to inspect uploaded files. Use
`chat.search-documents` for targeted extracted-content search and
`chat.get-document-markdown` when complete extracted markdown is needed. Use
`chat.wait-seconds` once when extraction is pending and the file is needed.

The main orchestration also exposes direct document-analysis tools such as
`chat.read-document` and `chat.extract-full-summary`; those are part of the
chat request tool surface, not the current skill `allowed_tools` list.

Call `agent.chat.stats-agent` for current statistics. Call
`agent.chat.component-agent` when the user asks to display UI components.

Use `chat.search-messages` for older persisted conversation details outside the
recent message window.

When required structured values should come from the user, call `core.ask-user`
with a flat Form model. Use Form field type `select` for dropdown controls.
```

The skill is instruction-only. Runtime behavior stays in actions and tools.

## Separation Of Responsibilities

| Layer | Responsibility |
| --- | --- |
| Action | Persist messages, publish UI updates, call `generate_stream(...)`. |
| Tool | Read or write one bounded piece of module/platform state. |
| Agent | Register focused runtime behavior and allowed tool surface. |
| Skill | Provide reusable operational guidance to the model. |
