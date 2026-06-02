# Progress and Confirmation

This page covers the task-state mutation methods used while a background job is already running:

- `update_progress(...)`
- `emit_progress(...)`
- `request_confirmation(...)`

These are the methods that make background tasks feel alive in the UI instead of looking like opaque fire-and-forget jobs.

## `update_progress(task_id, progress, checkpoint=None, label=None) -> None`

This method updates the progress metadata of a running task.

At minimum, that means the current numeric progress value. Optionally, it can also update the task label and attach a checkpoint payload that the runtime persists with the task.

### What It Is For

Use `update_progress(...)` when a background task has meaningful milestones that the user or another module may need to observe.

Good examples:

- a download reached 60%
- a multi-step install moved from "resolving metadata" to "writing files"
- an import processed 500 of 2,000 rows
- a task wants to persist a structured checkpoint before the next expensive phase

### What The Runtime Does With It

When the task exists, the runtime:

- clamps `progress` into the `0.0` to `1.0` range
- stores the new value on the task row
- optionally replaces the stored checkpoint
- optionally replaces the task label
- updates timestamps
- pushes a `backgroundTaskProgress` message to the connected user

That means the method is not just local bookkeeping. It is the main channel through which a running task keeps the UI informed.

## `emit_progress(task_id, progress=None, label=None, checkpoint=None) -> None`

This method pushes a live `backgroundTaskProgress` message to the connected user without updating the persisted task row.

Use it for high-frequency or ephemeral progress text that should be visible in the UI but should not create database churn.

Good examples:

- pip or package-manager output while installing an engine
- transient download log lines
- stream messages coming from a distributed worker or installer
- status lines that are useful now but not worth storing as the canonical task checkpoint

### Difference From `update_progress(...)`

`update_progress(...)` is the persisted checkpoint API. It updates the task record, timestamps, optional checkpoint payload, and then notifies the UI.

`emit_progress(...)` is a live notification API. It reuses the current task progress when `progress` is omitted, clamps explicit progress values to `0.0` through `1.0`, and sends the UI update without mutating the in-memory task object or writing the task row.

That distinction matters for noisy flows. An installer can emit many console lines per second, while only persisting meaningful milestones such as `installing`, `installed`, or `error`.

### Practical Example: Live Installer Output

```python
await module_sdk.tasks.update_progress(
    task_id,
    0.60,
    label="Installing engine dependencies",
)

await module_sdk.tasks.emit_progress(
    task_id,
    0.60,
    label="install: Collecting torch",
)
```

The first call records the milestone. The second call only refreshes the UI with the current live line.

### Missing Task Behavior

If the task id is unknown to the current task manager, the method returns without raising.

The caller should still treat that as an operational edge case, not a normal control path. Correct flows pass task ids returned by `run_background(...)` or resolved through task lookup helpers.

### Why The `label` Argument Is More Useful Than It Looks

The label is not only the static title of the task card. You can also use it as a live stage description.

Example:

```python
await module_sdk.tasks.update_progress(
    task_id,
    0.60,
    label="Downloading model weights",
)
```

Later:

```python
await module_sdk.tasks.update_progress(
    task_id,
    0.85,
    label="Writing registry metadata",
)
```

This is often more useful to the user than a bare percentage because it explains what the task is doing now.

### Practical Example: Stepwise Progress In A Demo Task

The demo background task under `modules/components/actions/background_task.py` uses the simplest possible pattern:

```python
async def _run_demo_task(module_sdk, task_ref: dict) -> None:
    steps = 10
    for i in range(1, steps + 1):
        await asyncio.sleep(1.5)
        task_id = task_ref["task_id"]
        if task_id:
            await module_sdk.tasks.update_progress(
                task_id,
                i / steps,
                label=f"Processing step {i}/{steps}...",
            )
```

This is a good teaching example because it shows the minimum viable discipline:

- progress moves monotonically
- the label explains the current stage
- the update happens inside the background coroutine, not back in the original action

### Practical Example: Real Engine Or Model Work

The system module uses the same idea in production-oriented helpers:

```python
await module_sdk.tasks.update_progress(task_id, 0.05, label=model_id)
...
await module_sdk.tasks.update_progress(
    task_id,
    0.60,
    label="Downloading model artifact",
)
...
await module_sdk.tasks.update_progress(task_id, 1.0, label=model_id)
```

The exact labels vary, but the important pattern is consistent: the task reports meaningful checkpoints as it moves across phases instead of saving all communication for the final success or failure event.

### The `checkpoint` Argument

`checkpoint` is for structured state that should travel with the task record.

Use it when the task monitor or a resume/debug flow benefits from more than a percentage and a label.

Example:

```python
await module_sdk.tasks.update_progress(
    task_id,
    0.40,
    checkpoint={
        "phase": "download",
        "downloaded_bytes": downloaded,
        "total_bytes": total,
    },
    label="Downloading source archive",
)
```

This is especially useful when you later inspect the task through `module_sdk.models.background_tasks.view(task_id)` and want the last known structured state.

### Important Behavior: Missing Task Is Ignored

If the task id does not exist in the current task manager, the method simply returns.

That is operationally convenient, but do not treat it as an excuse to guess task ids or skip lifecycle discipline. In correct module code, the task id should come from `run_background(...)` or a task lookup helper.

## `request_confirmation(task_id, builder) -> dict`

This method pauses a running background task and asks the user to confirm something through a UI surface built from a `Builder`.

This is one of the most powerful features in the domain because it lets a long-running job stop at a decision point without collapsing back into an action-driven flow.

### What It Is For

Use `request_confirmation(...)` when a background task discovers that it cannot continue safely without a user decision.

Practical examples:

- an import found duplicate keys and needs the user to choose merge or replace
- a model installer detected an existing artifact and asks whether to overwrite it
- a cleanup job found dependent rows and needs an explicit confirmation step

This is not for generic modal UI. It is specifically for task-time decisions inside an already-running background process.

### What The Runtime Does

When you call the method, the task manager:

- verifies the task exists
- moves the task status to `waiting_confirmation`
- serializes the builder components
- creates a dedicated confirmation surface id
- notifies the connected user with a `backgroundTaskConfirmation` message
- waits for the confirmation future to be resolved

The background coroutine is effectively paused until the user answers.

### Builder Requirement

The `builder` argument must be an SDK `Builder` instance whose components can be serialized into the confirmation surface.

Simple example:

```python
builder = module_sdk.ui.Builder()
builder.add(
    module_sdk.ui.Text(
        "confirm_text",
        "A model with the same name already exists. Replace it?",
    )
)
builder.add(
    module_sdk.ui.Button(
        "confirm_replace",
        label="Replace",
        action="system.task.confirm_replace",
    )
)
builder.add(
    module_sdk.ui.Button(
        "confirm_cancel",
        label="Cancel",
        action="system.task.confirm_cancel",
    )
)

decision = await module_sdk.tasks.request_confirmation(task_id, builder)
```

The exact actions and payload conventions depend on the confirmation flow you build, but the key point is that the task-owned UI is defined with the same SDK builder primitives used elsewhere in the application.

### Why This Is Better Than Aborting And Asking The User To Retry

Without task confirmation support, modules often end up with brittle flows like:

1. background task discovers a conflict
2. task fails
3. user must infer what happened
4. user retries through another action with extra flags

That is a poor background-task experience. `request_confirmation(...)` lets the task stay alive, surface the exact decision point, and continue once the user answers.

### Return Value

The method returns a `dict` with the confirmation response.

The exact shape depends on the confirmation-resolution path, so treat it as task-flow data rather than a fixed universal schema. In tests, the method is often mocked with a payload such as:

```python
{"ok": True, "components": comps}
```

In real module code, the important part is that your coroutine receives the resolved answer and can continue accordingly.

### Failure Mode

If the task manager is not initialized, the method raises `RuntimeError`.

If the task id does not exist, the lower-level runtime raises an error for the missing task. That is the right behavior: a confirmation request without a real running task is a contract bug, not a recoverable UX path.

## Practical Pattern: Progress Before And After Confirmation

A useful real-world pattern is:

1. update progress before the risky phase
2. ask for confirmation
3. resume work and update progress again

Example:

```python
await module_sdk.tasks.update_progress(
    task_id,
    0.55,
    checkpoint={"phase": "conflict_detected"},
    label="Conflict detected, waiting for confirmation",
)

decision = await module_sdk.tasks.request_confirmation(task_id, builder)

if decision.get("replace_existing"):
    await module_sdk.tasks.update_progress(
        task_id,
        0.65,
        label="Replacing existing artifact",
    )
```

This keeps the task monitor truthful. The user sees that the task did not freeze arbitrarily; it is intentionally waiting on a decision.

