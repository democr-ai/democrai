# Core Model: `background_tasks`

The `background_tasks` core model exposes task runtime state.

This model is read-only from the SDK perspective. It exists so modules can inspect task progress, status, and results, not so they can create synthetic task rows through generic CRUD.

## What This Model Represents

Rows include:

- `id`
- `module`
- `label`
- `status`
- `progress`
- `task_key`
- `user_id`
- `organization_id`
- `created_at`
- `updated_at`

Detail rows also include:

- `checkpoint`
- `result`
- `error`

## Typical Use Cases

Use `module_sdk.models.background_tasks` when you need to:

- show a task table
- count tasks by status for dashboards
- inspect one task’s failure or result payload

The `monitor` module uses it for task monitoring UI.

## Counting Tasks

Example:

```python
failed = module_sdk.models.background_tasks.count(
    filters={"status": "failed"}
)
```

This is a natural fit for summary cards and status badges.

## Listing Tasks

Example:

```python
listing = module_sdk.models.background_tasks.list(
    page=0,
    page_size=50,
    filters={"module": "system"},
)
```

Supported filters include:

- `id`
- `module`
- `label`
- `status`
- `task_key`
- `user_id`
- `organization_id`

The default sort is `updated_at desc`, which is what you usually want in a task monitor.

## Viewing One Task

Example:

```python
task = module_sdk.models.background_tasks.view(task_id)
```

Use this when a detail page needs the checkpoint, result, or error fields that are not present in the compact list row.

## Write Operations Are Disabled

This model is read-only:

- `create(...)` raises `NotImplementedError("background_tasks is read-only")`
- `update(...)` raises the same kind of error
- `delete(...)` raises the same kind of error

Background task state should be produced by the task runtime, not by generic model writes.

