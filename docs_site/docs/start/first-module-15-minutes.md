# First Module in 15 Minutes

This walkthrough creates a minimal but realistic `tickets` module.

It shows:

- the basic module tree
- one module-owned model
- one YAML-first page
- CRUD actions backed by `sdk.database`
- one tool
- one agent invoked through `sdk.ai.run_agent(...)`

This example uses **module-owned ticket data**, so it uses `sdk.database`, not `sdk.models`.

## 1. Create The Module Tree

```bash
mkdir -p modules/tickets/{actions,agents,tools,ui/yaml,locales}
touch modules/tickets/__init__.py
touch modules/tickets/actions/__init__.py
touch modules/tickets/agents/__init__.py
touch modules/tickets/tools/__init__.py
touch modules/tickets/ui/__init__.py
```

Suggested tree:

```text
modules/tickets/
  __init__.py
  manifest.json
  rbac.json
  models.py
  locales/
    en.json
  ui/
    __init__.py
    list.py
    yaml/
      tickets_list.yaml
  actions/
    __init__.py
    tickets.py
  tools/
    __init__.py
    tickets_tools.py
  agents/
    __init__.py
    tickets_agents.py
```

## 2. Create `manifest.json`

```json
{
  "name": "tickets",
  "label": "Tickets",
  "version": "1.0.0",
  "icon": "ric.ticket-2-line",
  "description": "Ticket management module",
  "priority": 80,
  "enabled": true,
  "allowed_imports": [],
  "access": []
}
```

## 3. Create `rbac.json`

`rbac.json` uses short permission names. The module namespace qualifies them at runtime.

```json
{
  "permissions": [
    "ticket.list",
    "ticket.view",
    "ticket.create",
    "ticket.update",
    "ticket.delete"
  ],
  "assignments": {
    "super": [
      "ticket.list",
      "ticket.view",
      "ticket.create",
      "ticket.update",
      "ticket.delete"
    ],
    "organization": [
      "ticket.list",
      "ticket.view",
      "ticket.create",
      "ticket.update"
    ],
    "user": [
      "ticket.view"
    ],
    "guest": []
  }
}
```

## 4. Create The Module Model

```python
from democrai.sdk.database import Base
from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column


class Ticket(Base):
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
```

Because the module base already includes the scope mixins, the SDK datastore will manage `user_id` and `organization_id` automatically. The module does not need to set them manually.

## 5. Create The YAML Page

`ui/yaml/tickets_list.yaml`

```yaml
- kind: Column
  id: tickets_root
  spacing: 12
  children:
    - kind: Title
      id: tickets_title
      text: "Tickets"
    - kind: DataTable
      id: tickets_table
      model: []
      rows: []
    - kind: Form
      id: ticket_form
      submit_label: "Create Ticket"
      action: "tickets.create_ticket"
      params:
        table_id: tickets_table
      model:
        - type: text
          name: title
          label: "Title"
          required: true
        - type: textarea
          name: description
          label: "Description"
          required: true
        - type: select
          name: status
          label: "Status"
          value: open
          options:
            - value: open
              label: "Open"
            - value: closed
              label: "Closed"
```

Two details matter here:

- child components stay nested under `children`
- `Form.action` is the action name string, and extra context goes in `params`

## 6. Create The Render Entry

`ui/list.py`

```python
from democrai.sdk.client import active_sdk as sdk

from modules.tickets.models import Ticket


def _ticket_row(ticket: Ticket) -> dict:
    return {
        "id": ticket.id,
        "title": ticket.title,
        "description": ticket.description,
        "status": ticket.status,
    }


async def render(params: dict, session: dict):
    builder = sdk.ui.load("ui/yaml/tickets_list")
    table = builder.get_component("tickets_table")
    if table is None:
        return builder

    table.set_property(
        "model",
        [
            {"name": "id", "label": "ID"},
            {"name": "title", "label": "Title"},
            {"name": "description", "label": "Description"},
            {"name": "status", "label": "Status"},
        ],
    )
    table.set_property(
        "rows",
        [_ticket_row(ticket) for ticket in sdk.database.list(Ticket)],
    )
    return builder
```

This keeps the page YAML-first while still allowing runtime data injection.

## 7. Add CRUD Actions

`actions/tickets.py`

```python
from democrai.sdk.decorators import action
from democrai.sdk.auth import permission_required

from modules.tickets.models import Ticket


def _ticket_row(ticket: Ticket) -> dict:
    return {
        "id": ticket.id,
        "title": ticket.title,
        "description": ticket.description,
        "status": ticket.status,
    }


@action("create_ticket")
@permission_required(["tickets.ticket.create"])
async def create_ticket(ctx: dict, session: dict, module_sdk):
    values = dict(ctx.get("values") or {})

    row = module_sdk.database.add(
        Ticket(
            title=str(values.get("title") or "").strip(),
            description=str(values.get("description") or "").strip(),
            status=str(values.get("status") or "open").strip() or "open",
        )
    )

    rows = [_ticket_row(ticket) for ticket in module_sdk.database.list(Ticket)]
    return module_sdk.effects.respond(
        module_sdk.effects.notify(
            "toast",
            {"title": "Created", "text": "Ticket created", "variant": "success"},
        ),
        module_sdk.effects.ui_property_update("tickets_table", "rows", rows),
        module_sdk.effects.ui_property_update("ticket_form", "values", {}),
    )


@action("update_ticket")
@permission_required(["tickets.ticket.update"])
async def update_ticket(ctx: dict, session: dict, module_sdk):
    ticket_id = int(ctx.get("id") or 0)
    values = dict(ctx.get("values") or {})

    row = module_sdk.database.update(
        Ticket,
        ticket_id,
        title=str(values.get("title") or "").strip(),
        description=str(values.get("description") or "").strip(),
        status=str(values.get("status") or "open").strip() or "open",
    )
    if row is None:
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {"title": "Not found", "text": "Ticket not found", "variant": "error"},
            )
        )

    return module_sdk.effects.respond(
        module_sdk.effects.notify(
            "toast",
            {"title": "Saved", "text": "Ticket updated", "variant": "success"},
        ),
        module_sdk.effects.render(),
    )


@action("delete_ticket")
@permission_required(["tickets.ticket.delete"])
async def delete_ticket(ctx: dict, session: dict, module_sdk):
    ticket_id = int(ctx.get("id") or 0)
    deleted = module_sdk.database.delete(Ticket, ticket_id)

    if not deleted:
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {"title": "Not found", "text": "Ticket not found", "variant": "error"},
            )
        )

    rows = [_ticket_row(ticket) for ticket in module_sdk.database.list(Ticket)]
    return module_sdk.effects.respond(
        module_sdk.effects.notify(
            "toast",
            {"title": "Deleted", "text": "Ticket removed", "variant": "success"},
        ),
        module_sdk.effects.ui_property_update("tickets_table", "rows", rows),
    )
```

This is already enough for a useful module:

- writes go through `sdk.database`
- scope is enforced automatically
- the action returns effects through `sdk.effects.respond(...)`

## 8. Add A Tool

`tools/tickets_tools.py`

```python
from democrai.sdk.decorators import tool

from modules.tickets.models import Ticket


@tool(
    name="tickets.lookup-ticket",
    description="Load one ticket by id",
    input_schema={
        "type": "object",
        "properties": {
            "id": {"type": "integer"},
        },
        "required": ["id"],
    },
)
async def lookup_ticket(id: int, *, sdk=None, context: dict | None = None):
    if sdk is None:
        return {"status": "error", "error": "missing_sdk"}

    ticket = sdk.database.get(Ticket, int(id))
    if ticket is None:
        return {"status": "error", "error": "not_found"}

    return {
        "status": "ok",
        "ticket": {
            "id": ticket.id,
            "title": ticket.title,
            "description": ticket.description,
            "status": ticket.status,
        },
    }
```

## 9. Add An Agent

`agents/tickets_agents.py`

```python
from democrai.sdk.decorators import agent


@agent(
    name="tickets.triage-agent",
    description="Classify incoming ticket requests",
    objective="chat",
    tools=["tickets.lookup-ticket"],
    max_iterations=3,
)
async def triage_agent(input: str = "", sdk=None, context: dict | None = None):
    if sdk is None:
        return {"content": "SDK unavailable"}

    messages = [
        {
            "role": "system",
            "content": (
                "You are a ticket triage agent. Use ticket lookup tools when "
                "ticket data is needed before answering."
            ),
        },
        {"role": "user", "content": str(input or "")},
    ]
    result = await sdk.ai.get_provider_for_objective("support")
    if result.get("status") != "ok":
        raise RuntimeError(result.get("error", "Provider unavailable"))
    response = await result["provider"].generate_completion(
        messages=messages,
        options={
            "tools": [
                sdk.ai.get_tool("tickets.lookup-ticket").to_completion_tool()
            ],
        },
    )
    return {"content": str(response.get("content") or "")}
```

The important point is the integration contract:

- the tool is registered independently
- the agent declares it in `tools=[...]`
- the runtime can use that tool during agent execution
- in a custom handler, the declared tools are still available through the agent-aware completion helpers

## 10. Invoke The Agent From An Action

```python
from democrai.sdk.decorators import action


async def handle_agent_event(event: dict):
    event_type = str(event.get("type") or "")
    if event_type == "agent.tool.finished":
        result = dict(event.get("result") or {})
        # here you can publish live UI updates, logs, or telemetry


@action("ask_triage_agent")
async def ask_triage_agent(ctx: dict, session: dict, sdk):
    prompt = str(ctx.get("prompt") or "").strip()
    ticket_id = ctx.get("ticket_id")

    result = await sdk.ai.run_agent(
        "tickets.triage-agent",
        input=prompt,
        context={"ticket_id": ticket_id, "source": "tickets.list"},
        listener=handle_agent_event,
    )

    content = str(getattr(result, "content", None) or result.get("content") or "")
    return sdk.effects.respond(
        sdk.effects.ui_property_update(
            "tickets_title",
            "text",
            {"literalString": content},
        )
    )
```

This is the normal usage. `sdk.ai.run_tool(...)` is only for explicit manual orchestration when that is really what you want.

The listener is optional, but useful when the action wants to observe:

- run start/finish
- tool input/output
- completion lifecycle
- stream chunks
