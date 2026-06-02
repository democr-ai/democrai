# Chat Module RBAC And Locales

This step adds authorization and translations to the module.

At this point the folder contains the manifest and models. Before creating UI
and actions, define who can open the chat and who can write to it.

## Add RBAC

Create `modules/chat/rbac.json`:

```json
{
  "permissions": [
    "chat.view",
    "chat.write"
  ],
  "assignments": {
    "super": [
      "chat.view",
      "chat.write"
    ],
    "organization": [
      "chat.view",
      "chat.write"
    ],
    "user": [
      "chat.view",
      "chat.write"
    ],
    "guest": []
  }
}
```

The module uses two permissions:

| Permission | Purpose |
| --- | --- |
| `chat.view` | Allows opening chat pages and reading thread data. |
| `chat.write` | Allows creating threads, sending messages, loading the agent, and mutating the conversation. |

Keep permissions coarse enough to be understandable. The first version of the
chat has only two user-facing capabilities: read the chat workspace and write
into it.

`assignments` maps default roles to permissions. The chat is available to
authenticated users and hidden from guests:

- `super`, `organization`, and `user` receive both permissions;
- `guest` receives none.

The runtime syncs this file when the module is loaded. The module code still
has to declare which views and actions require each permission.

## Use Permissions In Page Entrypoints

The chat index page is read-only from the authorization point of view: it renders
the shell, existing threads, and the initial composer.

`modules/chat/ui/index.py` uses `chat.view`:

```python
from democrai.sdk.auth import permission_required
from democrai.sdk.decorators import page


@page("index")
@permission_required(["chat.view"])
async def render(ctx: dict, session: dict, sdk):
    ...
```

The thread page also uses `chat.view`:

```python
from democrai.sdk.auth import permission_required
from democrai.sdk.decorators import page


@page("thread/[id]")
@permission_required(["chat.view"])
async def render(ctx: dict, session: dict, sdk):
    ...
```

Page permissions protect access to the rendered surfaces. They do not replace
action permissions.

## Use Permissions In Actions

Actions that only read state use `chat.view`.

For example, opening an attachment preview reads an attachment and returns a UI
effect:

```python
from democrai.sdk.auth import permission_required
from democrai.sdk.decorators import action


@action("open_attachment_preview")
@permission_required(["chat.view"])
async def open_attachment_preview(ctx: dict, session: dict, module_sdk):
    ...
```

Actions that mutate a conversation use `chat.write`.

Sending a message persists a user turn, links attachments, starts model
execution, streams transient progress, and persists the final assistant response:

```python
from democrai.sdk.auth import permission_required
from democrai.sdk.decorators import action


@action("submit_message")
@permission_required(["chat.write"])
async def submit_message(ctx: dict, session: dict, module_sdk):
    ...
```

The same rule applies to the first-message action used by the home page:

```python
@action("start_thread")
@permission_required(["chat.write"])
async def start_thread(ctx: dict, session: dict, module_sdk):
    ...
```

The split between `start_thread` and `submit_message` matters later:

- the home page action creates the conversation and navigates to the thread;
- the thread page action appends to the current thread without navigation.

Both require `chat.write`, but they update the UI differently.

## Add Locales

Create one JSON file per supported language:

```text
modules/chat/locales/
  de.json
  en.json
  es.json
  fr.json
  it.json
  zh.json
```

Start with the English file.

`modules/chat/locales/en.json`:

```json
{
  "chat.sidebar.title": "Threads",
  "chat.home.title": "Chat",
  "chat.home.knowledge_note": "Document retrieval uses knowledge when available; uploaded documents can still be read from extracted markdown.",
  "chat.composer.placeholder": "Write a message or attach documents...",
  "chat.thread.untitled": "New chat",
  "chat.attachments.title": "Attachments",
  "chat.attachments.name": "Name",
  "chat.attachments.mime": "MIME",
  "chat.toast.empty_message": "Write a message or attach a file before sending.",
  "chat.sidebar.new": "New",
  "chat.home.status.ready": "Ready",
  "chat.agent.status.running": "Agent is working",
  "chat.agent.status.started": "Preparing the answer.",
  "chat.agent.status.completed": "Agent completed",
  "chat.agent.status.failed": "Agent failed",
  "chat.composer.reasoning": "Reasoning"
}
```

The Italian file mirrors the same keys:

```json
{
  "chat.sidebar.title": "Thread",
  "chat.home.title": "Chat",
  "chat.home.knowledge_note": "Il retrieval sui documenti usa la knowledge quando disponibile; i documenti caricati restano leggibili dal markdown estratto.",
  "chat.composer.placeholder": "Scrivi un messaggio o allega documenti...",
  "chat.thread.untitled": "Nuova chat",
  "chat.attachments.title": "Allegati",
  "chat.attachments.name": "Nome",
  "chat.attachments.mime": "MIME",
  "chat.toast.empty_message": "Scrivi un messaggio o allega un file prima di inviare.",
  "chat.sidebar.new": "Nuova",
  "chat.home.status.ready": "Pronta",
  "chat.agent.status.running": "L'agente sta lavorando",
  "chat.agent.status.started": "Preparazione della risposta.",
  "chat.agent.status.completed": "Agente completato",
  "chat.agent.status.failed": "Agente in errore",
  "chat.composer.reasoning": "Reasoning"
}
```

YAML pages reference translations with `@t/...`:

```yaml
- kind: Text
  id: chat_sidebar_title
  text: "@t/chat.sidebar.title"
```

Python code uses the SDK i18n helper:

```python
module_sdk.i18n.t("chat.toast.empty_message")
```

Use translation keys for every visible label, placeholder, toast, and status
message. Do not hardcode user-facing text in actions or YAML when the text is
part of the module UI.

Next we will create the first YAML page and render it from `ui/index.py`.
