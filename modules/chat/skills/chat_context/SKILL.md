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

Use this skill in the chat module.

The main chat request is the conversation router. It sees recent messages and the
thread summary, uses direct tools for document retrieval, and delegates focused
statistics or component work to subagents.

When the user references an uploaded file, use `chat.list-attachments` to inspect
attachment and extraction status. Use `chat.search-documents` for targeted
questions over extracted content, `chat.get-document-markdown` when complete
extracted markdown is needed, and `chat.wait-seconds` once when extraction is
pending and the file is needed.

When the user asks for current statistics, counts, monitoring, or dashboard
data, call `agent.chat.stats-agent`.

When the user asks to display UI components, call `agent.chat.component-agent`
with compact data. The component agent owns the specialized component tools.

Use `chat.search-messages` to recover older persisted conversation details that
are outside the recent message window.

When required structured values should come from the user, call `core.ask-user`
with a Form model. Do not simulate HITL with plain text instructions, and do not
refer to `agent_hitl_form` as a tool name. The Form model must be a flat list of
fields; do not use row, column, children, or nested layout nodes. For dropdown
controls, use Form field type `select` with an `options` array; `dropdown` is not
a supported field type.
