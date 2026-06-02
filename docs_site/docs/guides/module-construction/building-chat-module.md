# Building The Chat Module

This tutorial builds the `chat` module as a complete conversation workspace:
persistent threads, YAML-first pages, streaming answers, attachments, document
retrieval, focused subagents, a reusable skill, and persisted A2UI component
messages.

The snippets are intentionally representative rather than a full copy of
`modules/chat`. The contracts, file shape, action names, bindings, and SDK
boundaries match the current module.

## Tutorial Roadmap

| Step | What we add | Why it comes here |
| --- | --- | --- |
| Folder and manifest | Module identity and runtime discovery | The module must load before routes, models, actions, tools, and agents matter. |
| Models | `Conversation`, `Message`, `Attachment`, `ChatComponent` | Persistence defines thread state, timeline rows, upload links, and A2UI output. |
| RBAC and locales | `chat.view`, `chat.write`, translated UI strings | Pages and actions need stable permission and text keys. |
| Home UI | Shared chat shell with empty timeline and composer | The user starts before a thread exists. |
| Thread UI | Same shell with current thread state, pagination, and timeline window | The active thread needs stable layout and incremental updates. |
| Actions | Send, stream, paginate, rename, delete, preview, stop | UI events become persistent behavior. |
| Orchestration | Provider messages, options, tools, skills, agents, streaming callbacks | The LLM call stays bounded and observable. |
| Tools | Attachments, document reading, retrieval, stats, component creation | The model gets scoped capabilities instead of direct database or core access. |
| Agents and skill | Stats/component subagents, title/summary assets, chat guidance | Runtime assets become discoverable and explicit. |
| Integration | Discovery, boundaries, generated migration, completion checks | The module is ready to run as one coherent feature. |

## 1. Start With The Module Folder

Create the module under `modules/chat/`:

```text
modules/chat/
  __init__.py
  manifest.json
  rbac.json
  models.py
  actions/
    __init__.py
    attachments.py
    conversation.py
  agents/
    __init__.py
    component.py
    stats.py
    summary.py
    title.py
  locales/
    en.json
    ...
  skills/
    chat_context/
      SKILL.md
  tools/
    __init__.py
    attachments.py
    components.py
    retrieval.py
    stats.py
    wait.py
  ui/
    __init__.py
    index.py
    thread/
      __init__.py
      [id].py
      [_id]/
        rename.py
  utils/
    actions/
      a2ui_schema.py
      attachments.py
      components.py
      conversation.py
      messages.py
      orchestration.py
    ui/
      mime.py
      rows.py
      state.py
      yaml/
        index.yaml
        thread.yaml
        thread_rename.yaml
```

Migrations are generated from `models.py`. The tutorial designs the model shape
first, then lets the migration tooling produce files under `migrations/`.

## 2. Add The Manifest

Create `modules/chat/manifest.json`:

```json
{
  "name": "chat",
  "label": "Chat",
  "version": "0.1.0",
  "icon": "ric.message-3-line",
  "description": "Conversation workspace with document-aware attachments.",
  "priority": 30,
  "enabled": true,
  "allowed_imports": [],
  "access": []
}
```

The chat module does not request direct filesystem or network access. Uploads,
media URLs, knowledge retrieval, AI execution, tasks, and UI updates go through
SDK domains.

## Manifest Notes

Keep `name` stable. It scopes routes, action names, translations, RBAC,
database table prefixes, skills, tools, and agents.

Keep `allowed_imports` and `access` empty unless the module has a reviewed need
outside SDK services. A chat module should not request raw filesystem or network
permissions just because it can upload files or call an AI provider through the
runtime.

If a future chat extension needs a managed secret, declare it in `environment`
and read it through the environment SDK. Do not read provider credentials from
local files or environment variables ad hoc.
