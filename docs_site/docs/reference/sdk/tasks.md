# SDK Domain: `tasks`

## Overview

The `tasks` domain is the SDK surface for work that either runs outside the immediate request/response flow or would otherwise block it badly enough to hurt the runtime.

That sounds like a narrow concern, but in practice it covers three different problems that module authors often mix together:

- detached background work that must keep running after the action already returned
- blocking synchronous work that should stay inside the current action, but off the event loop
- task-state inspection for progress UIs, dashboards, and deduplication logic

Keeping those three cases separate is the difference between a task flow that feels solid and one that produces duplicate jobs, frozen actions, or background cards that never update correctly.

## What This Domain Is For

Use `module_sdk.tasks` when your module needs to:

- submit a long-running job and immediately return control to the UI
- keep a progress bar updated while the job is running
- temporarily pause a background flow and ask the user to confirm a choice
- move a blocking synchronous function or subprocess off the event loop
- fetch tasks by user or by logical key so the UI can reconnect to existing work

Typical examples in this repository include:

- engine installation flows
- model download or materialization flows
- long-running inventory or ingestion jobs
- demo task cards rendered with the `BackgroundTask` UI component

## What This Domain Is Not

This domain is not a generic replacement for every asynchronous operation.

Do not reach for `sdk.tasks` when:

- the operation is quick and belongs entirely inside the action
- you only need to return UI effects such as a toast or a render
- you want to query historical task rows with rich filters and detail fields

For those cases:

- use `sdk.effects` to mutate the UI
- use `sdk.models.background_tasks` to build list/detail views over persisted task state

That split matters. `sdk.tasks` is the orchestration API. `sdk.models.background_tasks` is the read model.

## The Facade Mental Model

The public surface is intentionally small:

- `run_background(...)`
- `run_blocking(...)`
- `run_subprocess(...)`
- `update_progress(...)`
- `emit_progress(...)`
- `request_confirmation(...)`
- `list_user_tasks(...)`
- `get_tasks_by_key(...)`
- `get_tasks_by_key_prefix(...)`

The facade does more than just forward calls. It preserves request context, carries the current module identity into the task runtime, and keeps sandbox restrictions aligned with the module that started the work. That is why module code should use the SDK facade instead of trying to import task-manager internals directly.

## The Most Important Distinction

The easiest mistake is choosing between `run_background(...)` and `run_blocking(...)` incorrectly.

Use `run_background(...)` when the work is a real background job and the action should return immediately with a task id or a `BackgroundTask` component.

Use `run_blocking(...)` when the work is still part of the current action result, but the implementation is synchronous and would otherwise block the event loop. In that case the caller still waits for the result; the only difference is that the blocking code runs in a worker thread.

`run_subprocess(...)` sits next to `run_blocking(...)`: the action still waits for the subprocess result, but the subprocess is launched through the SDK so sandbox and request context stay correct.

## Recommended Flow For Real Background Jobs

For most module authors, the healthy pattern is:

1. validate the input inside the action
2. submit the background job with `run_background(...)`
3. return UI effects immediately, usually including a `BackgroundTask` card or a render update
4. inside the background coroutine, call `update_progress(...)` at meaningful checkpoints
5. inspect task state later either with task lookup helpers or through `module_sdk.models.background_tasks`

That is the pattern used by the engine/model flows in `modules/system`.

## Subsections

This domain is split into focused pages:

- [Running Background Work](./tasks/running-background-work.md)
- [Progress and Confirmation](./tasks/progress-and-confirmation.md)
- [Querying Task State](./tasks/querying-task-state.md)

Read them in that order if you are implementing a new background workflow from scratch.

