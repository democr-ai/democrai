# Commands

Commands are module functions registered for runtime execution outside a direct
UI event. Use them when work belongs to the module but should be started by the
runtime rather than by a button click.

They live under:

```text
modules/<module>/commands/
  __init__.py
  *.py
```

The module loader discovers files in `commands/` and imports them during module
loading. Command decorators register the callable in the module command
registry.

## Command Types

The SDK exposes four command decorators:

| Decorator | Lifecycle | Use it for |
| --- | --- | --- |
| `@callable_command(...)` | on demand | A command invoked explicitly by runtime tooling. |
| `@single_run_command(...)` | startup once | Boot-time module initialization that should run and exit. |
| `@scheduled_command(...)` | schedule | Repeated work triggered by cron or fixed interval. |
| `@long_run_command(...)` | long running | A module process that should stay alive after boot. |

Commands are not UI actions. If a user interaction needs an immediate UI
response, implement an action and return effects. If the action needs background
work, have the action enqueue/start that work through the SDK and keep the
command focused on the background behavior.

## Callable Command

Create `modules/<module>/commands/maintenance.py`:

```python
from __future__ import annotations

from democrai.sdk.decorators import callable_command


@callable_command("rebuild_index")
async def rebuild_index(module_sdk):
    records = module_sdk.database.list(MyModel)
    for record in records:
        ...
```

The registered name is module-qualified by the SDK. In module `reports`,
`rebuild_index` becomes `reports.rebuild_index`.

Use callable commands for explicit operational tasks. Do not expose user-facing
form flows through commands.

## Single Run Command

Use `single_run_command` for startup work that should run once and finish:

```python
from __future__ import annotations

from democrai.sdk.decorators import single_run_command


@single_run_command("sync_defaults")
async def sync_defaults(module_sdk):
    existing = MyModel.count(filters={"kind": "default"})
    if existing:
        return
    module_sdk.database.add(MyModel(kind="default", name="Default"))
```

Keep this work idempotent. The function may be re-evaluated across development
reloads or deployment changes, so it should be safe to call again.

## Scheduled Command

Use `scheduled_command` for repeated module work:

```python
from __future__ import annotations

from democrai.sdk.decorators import scheduled_command


@scheduled_command("refresh_metrics", interval_seconds=300)
async def refresh_metrics(module_sdk):
    rows = module_sdk.database.list(MyModel, filters={"stale": True})
    for row in rows:
        ...
```

The decorator accepts either an interval or a cron expression:

```python
@scheduled_command("daily_rollup", cron="0 2 * * *")
async def daily_rollup(module_sdk):
    ...
```

Use one scheduling mechanism per command. Keep the command bounded: one
scheduled tick should do a clear unit of work and then return.

## Long Running Command

Use `long_run_command` only when the module really owns a long-lived worker:

```python
from __future__ import annotations

from democrai.sdk.decorators import long_run_command


@long_run_command("watch_queue", restart_on_exit=True)
async def watch_queue(module_sdk):
    async for item in module_sdk.tasks.consume("reports.queue"):
        ...
```

Long-running commands should cooperate with shutdown, avoid blocking the event
loop, and use SDK services for queues, tasks, storage, and platform state.

## Boundary Rules

Commands follow the same module boundary as actions:

- use SDK domains for database, media, tasks, AI, knowledge, events, and system
  state;
- keep module-owned persistence in module models;
- do not import core services or client code;
- do not load AI models directly in the module process;
- keep user-facing UI updates in actions or event/stream effects, not in
  command bodies.

## When Not To Use Commands

Do not use commands for:

- button clicks;
- composer submit flows;
- navigation;
- streaming chat responses;
- direct replacement for a task queue;
- hidden business logic that actions and tools cannot explain.

For user-triggered work, start with an action. For agent-callable capabilities,
start with a tool. For runtime lifecycle work, use a command.
