# Querying Task State

This page covers the read-side helpers exposed directly by `module_sdk.tasks`:

- `list_user_tasks(...)`
- `get_tasks_by_key(...)`
- `get_tasks_by_key_prefix(...)`

These methods exist for operational lookups and reconnection flows. They are not a replacement for the richer read model available through `module_sdk.models.background_tasks`.

## Read This Distinction First

There are two valid ways to inspect task state in module code, and they serve different purposes.

Use `module_sdk.tasks.*` lookup helpers when:

- you already know the user id or the logical task key
- you want lightweight runtime-facing lookup behavior
- you are reconnecting UI components to known task ids or known task families

Use `module_sdk.models.background_tasks` when:

- you need paginated tables
- you need rich filtering by model fields
- you need task detail pages with `checkpoint`, `result`, or `error`
- you are building a proper monitoring UI

The lookup helpers are close to orchestration. The model proxy is the reporting surface.

## `list_user_tasks(user_id, organization_id=None) -> list[dict]`

This method returns serialized tasks visible to a specific user.

### What It Is For

Use it when the module needs to recover active or recent task information for a known user without writing a broader task-monitor query.

Typical examples:

- reconnecting a dashboard widget after a page reload
- rehydrating a task area when the module already knows the authenticated user id
- checking whether the user already has visible running work before starting another flow

### Practical Example

```python
user = dict(session.get("user") or {})
user_id = int(user.get("id") or 0)
organization_id = user.get("organization_id")

tasks = module_sdk.tasks.list_user_tasks(
    user_id,
    organization_id=organization_id,
)
```

The returned values are already serialized dictionaries, which makes them easy to pass into a builder data model or transform into task cards.

### Runtime Behavior

If the task manager is missing or the underlying call raises, the method returns an empty list.

That makes it suitable for operational lookups in UI code where “no visible tasks” is usually a reasonable default.

## `get_tasks_by_key(task_key, organization_id=None) -> list[dict]`

This method returns serialized tasks whose logical key matches exactly.

### Why Exact-Key Lookup Matters

A generated task id is only useful after the task exists. A logical key is useful before, during, and after the task exists because it describes the work semantically.

That makes exact-key lookup the natural companion to `run_background(..., task_key=...)`.

Example:

```python
existing = module_sdk.tasks.get_tasks_by_key(
    f"system.model.catalog.materialize.{catalog_id}",
    organization_id=organization_id,
)
```

This lets a module or page ask a question like:

`"Do we already have a task for catalog model 42?"`

instead of:

`"Do we know the UUID of whatever task might already exist?"`

### Returned Order

The runtime sorts the tasks by `created_at` descending before serializing them.

That means the first row is the newest matching task, which is usually what you want when reconnecting to the most recent run of a logical job.

### Practical Example: Reconnect To The Current Task Card

Imagine a page that should show the current materialization task for a catalog model if one is already running or recently ran:

```python
task_rows = module_sdk.tasks.get_tasks_by_key(
    f"system.model.catalog.materialize.{catalog_id}",
    organization_id=session.get("user", {}).get("organization_id"),
)

latest = task_rows[0] if task_rows else None
if latest:
    builder.add(
        module_sdk.ui.BackgroundTask(
            f"catalog_task_{latest['id']}",
            task_id=latest["id"],
        )
    )
```

That is exactly the kind of UI recovery logic these helpers are meant to support.

## `get_tasks_by_key_prefix(prefix, organization_id=None) -> list[dict]`

This method returns serialized tasks whose `task_key` starts with the provided prefix.

### What It Is For

Use prefix lookup when your module intentionally names task families with a shared prefix and later wants to inspect them as a group.

Examples:

- all install tasks for a provider
- all model materialization tasks for a module area
- all jobs associated with a specific entity namespace

### Naming Strategy Matters

Prefix lookup only becomes useful if the original keys were designed with hierarchy in mind.

Good pattern:

```text
system.engine.install.openai.12
system.engine.install.openai.13
system.engine.install.ollama.4
```

Now a prefix like `system.engine.install.` or `system.engine.install.openai.` becomes meaningful.

### Practical Example: Show Recent Jobs For A Provider

```python
provider_tasks = module_sdk.tasks.get_tasks_by_key_prefix(
    f"system.engine.install.{provider}.",
    organization_id=session.get("user", {}).get("organization_id"),
)
```

This gives the UI a lightweight way to populate a "recent installs for this provider" panel without dropping straight into a richer model-monitor query.

### Returned Order

Like exact-key lookup, prefix results are sorted by `created_at` descending before serialization.

That is convenient because grouped task views usually care first about the newest runs.

## What These Serialized Rows Are Good For

The serialized task dictionaries are well-suited for:

- reconnecting a `BackgroundTask` component using the `id`
- showing lightweight task summaries in a page
- deciding whether to start a new task or attach to an existing one

They are less suited for:

- building a full monitoring table with pagination
- advanced status analytics
- deep inspection of result/error payloads across many rows

For those cases, switch to `module_sdk.models.background_tasks`.

## Practical Pattern: Combine Lookup With The Read Model

A strong pattern is:

1. use `task_key` when submitting work
2. use `get_tasks_by_key(...)` or `get_tasks_by_key_prefix(...)` to reconnect the page quickly
3. use `module_sdk.models.background_tasks.view(task_id)` if the user opens a detail panel and needs checkpoint, result, or error

That keeps the orchestration code simple while still giving the UI an upgrade path into richer inspection.

