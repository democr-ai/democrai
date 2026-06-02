# Running Background Work

This page covers the execution-side methods of `module_sdk.tasks`:

- `run_background(...)`
- `run_blocking(...)`
- `run_subprocess(...)`

They all move work away from the hot path of the event loop, but they solve different problems. If you keep that distinction clear, the rest of the API becomes straightforward.

## `run_background(coro, label="Background Task", **kwargs) -> str`

This is the method you use when the work must keep going after the action already returned.

The runtime creates a task row, assigns it to the current authenticated user, schedules the coroutine, and immediately returns the generated task id. The UI can then attach to that task id with a `BackgroundTask` component or by querying task state later.

### What It Is For

Use `run_background(...)` when the operation is long enough that waiting for the action result would be the wrong UX or the wrong runtime shape.

Good fits:

- downloading or materializing models
- large imports
- document ingestion pipelines
- report generation
- multi-step synchronization jobs

Weak fit:

- a synchronous helper that takes 150 ms and is still needed to build the immediate response

That weaker case belongs to `run_blocking(...)`, not here.

### What It Accepts

The first argument may be one of two things:

- a coroutine object
- a registered task name as `str`

If you pass a string, the runtime resolves it through the task registry and invokes the registered task function with `**kwargs`.

If you pass a coroutine object, the coroutine is scheduled directly.

### Why You Should Use It Instead Of Spawning Work Manually

The task runtime does more than `asyncio.create_task(...)`.

It also:

- binds the task to the current user and organization
- persists task state
- sends task lifecycle updates to the connected client
- preserves request context for the task
- applies module sandbox restrictions during execution
- deduplicates active work when you provide a logical `task_key`

If you bypass the SDK and spawn free-floating coroutines yourself, you lose most of that behavior immediately.

### The `label` Argument

`label` is the user-facing task name.

It is what the client typically shows in task cards, monitors, and notifications. Keep it descriptive and specific enough that the user can tell one job from another.

Weak:

```python
label="Task"
```

Better:

```python
label=f"Download catalog model: {entry['label']}"
```

### The Important `kwargs`

The public signature only names `label`, but background submissions commonly rely on additional keyword arguments.

The most important one is `task_key`.

Example:

```python
task_id = await module_sdk.tasks.run_background(
    create_catalog_inventory_background(
        module_sdk,
        task_ref=task_ref,
        row_id=row_id,
        catalog_id=catalog_id,
    ),
    label=f"Download catalog model: {entry['label']}",
    task_key=f"system.model.catalog.materialize.{catalog_id}",
)
```

This pattern is used by the system module for catalog materialization.

### Why `task_key` Matters

`task_key` gives the runtime a logical identifier for the work, separate from the generated task id.

That helps in three common situations:

- deduplicating active tasks so repeated clicks do not start the same job twice
- reconnecting the UI to an already-running task
- grouping related task history later with `get_tasks_by_key(...)` or `get_tasks_by_key_prefix(...)`

The runtime deduplicates only active tasks. If an older task with the same key already completed or failed, a new submission can still create a new task.

### Real Example: Background Model Materialization

This repository uses `run_background(...)` in `modules/system/actions/model/index.py` to start catalog model materialization without freezing the action.

The flow is:

1. validate the catalog entry
2. create the `available_model_registry` row in status `materializing`
3. submit the background coroutine with a stable `task_key`
4. return a `BackgroundTask` card and a success toast immediately

The action shape looks like this:

```python
task_ref = {"task_id": ""}
task_id = await module_sdk.tasks.run_background(
    create_catalog_inventory_background(
        module_sdk,
        task_ref=task_ref,
        row_id=int(row.get("id") or 0),
        catalog_id=catalog_id,
    ),
    label=f"{module_sdk.i18n.t('system.model.catalog.action.download')}: {str(entry.get('label') or '')}",
    task_key=f"system.model.catalog.materialize.{catalog_id}",
)
task_ref["task_id"] = task_id
```

That `task_ref` detail is worth noticing. The coroutine needs the final task id later so it can call `update_progress(...)`, but the id only exists after submission. Passing a mutable holder is a simple and valid pattern when the background coroutine needs to learn its own runtime id after scheduling.

### Registered Task Name Example

When the work is registered in the task registry, you can submit it by name instead of constructing the coroutine directly:

```python
task_id = await module_sdk.tasks.run_background(
    "reports.generate_monthly",
    label="Generate monthly revenue report",
    task_key="reports.monthly.2026-04",
    month="2026-04",
    include_refunds=True,
)
```

This is useful when the background job is a reusable runtime task rather than a one-off coroutine local to the action.

### Return Value

The method returns the runtime task id as `str`.

That id is the thing you pass to:

- `update_progress(...)`
- `request_confirmation(...)`
- `sdk.ui.BackgroundTask(..., task_id=task_id)`
- any later task inspection flow

### Failure Modes To Expect

The two failures module authors hit most often are:

- no authenticated user in the session
- task manager not initialized

The first case matters because background tasks are owned by a user. If the current session has no `user.id`, submission fails.

## `run_blocking(func, *args, **kwargs) -> Any`

This method runs a synchronous callable in a worker thread and awaits the result.

The caller still waits for completion. Nothing becomes detached or persistent. The value of the method is that the blocking code stops blocking the event loop.

### What It Is For

Use `run_blocking(...)` when:

- you are inside an async action
- you still need the result before returning
- the implementation is synchronous and may block

Typical examples:

- heavy local file parsing
- CPU-heavy hashing or archive inspection
- library calls that are sync-only
- filesystem scans that would otherwise stall the request loop

### Why It Exists

The common temptation is to call a synchronous helper directly from an async action because the code "works" in development. The problem is that it blocks the event loop for the duration of the call. Under load, that turns into slow or stalled concurrent requests.

`run_blocking(...)` keeps the action shape simple while moving the blocking callable into a worker thread. It also preserves request/task runtime context while the callable runs.

### Practical Example: Parse A Large Uploaded Manifest

Imagine an action that receives a persisted upload reference, loads its bytes through `module_sdk.media.view(...)`, and parses a large manifest with a sync-only library before returning a preview.

```python
import json


def load_manifest(payload: bytes) -> dict:
    return json.loads(payload.decode("utf-8"))


@action("preview_manifest")
async def preview_manifest(ctx: dict, session: dict, module_sdk):
    storage_ref = str(ctx.get("storage_ref") or "").strip()
    payload = module_sdk.media.view(storage_ref)
    manifest = await module_sdk.tasks.run_blocking(load_manifest, payload)

    return module_sdk.effects.respond(
        module_sdk.effects.ui_messages(
            [
                module_sdk.ui.Builder.build_state_update_payload(
                    {"/manifest_preview": manifest},
                    scope="page",
                )
            ]
        )
    )
```

This should not be a background task because the user is waiting for the preview now. It should not run inline on the event loop because the parsing path is synchronous. `run_blocking(...)` is the right middle ground.


### When Not To Use It

Do not use `run_blocking(...)` as a substitute for real background orchestration.

If the UI should get a task id now and see progress later, use `run_background(...)`.

## `run_subprocess(command, *, cwd=None, check=False, text=True, capture_output=True, timeout=None, env=None) -> subprocess.CompletedProcess`

This method runs a subprocess under the module sandbox context and awaits the `CompletedProcess` result.

From a caller perspective it behaves much like `subprocess.run(...)`, but it is deliberately exposed through the SDK so the runtime can inject the correct sandbox and request-context information.

### Why This Method Exists

Subprocess execution is a sensitive boundary in this project.

Modules should not invent their own process-launching shortcuts because the runtime needs to preserve:

- the current module identity
- allowed filesystem paths
- allowed network targets
- request-scoped context

`run_subprocess(...)` is the supported path for that.

### Input Rules

The command must be a non-empty `list[str]`.

Good:

```python
result = await module_sdk.tasks.run_subprocess(
    ["ffmpeg", "-version"],
    text=True,
)
```

Wrong:

```python
result = await module_sdk.tasks.run_subprocess("ffmpeg -version")
```

The SDK validates this on purpose. It is not a shell-string API.

### What The Runtime Adds

The method injects sandbox-related environment variables so the child process inherits the correct module execution constraints.

That means it is suitable when the subprocess must operate as part of module-owned work instead of as an unrestricted host-level command.

### Practical Example: Probe A Local Media Tool

Suppose a module needs to verify that a local transcoding tool is present before enabling an import path:

```python
result = await module_sdk.tasks.run_subprocess(
    ["ffmpeg", "-version"],
    check=True,
    text=True,
)

version_line = (result.stdout or "").splitlines()[0]
```

This is still not a background task. The action is waiting for the answer immediately, but subprocess execution is routed through the SDK instead of raw `subprocess.run(...)`.

### Another Example: Run A Tool In A Specific Working Directory

```python
result = await module_sdk.tasks.run_subprocess(
    ["tar", "-tf", "bundle.tar"],
    cwd=workspace_dir,
    check=True,
    text=True,
)

entries = [line for line in (result.stdout or "").splitlines() if line]
```

The method forwards familiar `subprocess.run(...)` knobs such as:

- `cwd`
- `check`
- `text`
- `capture_output`
- `timeout`
- `env`

Use them exactly for the same reasons you would in standard Python, but keep the command in list form.

## Choosing The Right Execution Method

Use this quick rule:

- `run_background(...)`: the action should return now and the work should continue
- `run_blocking(...)`: the action must wait, but the implementation is blocking Python code
- `run_subprocess(...)`: the action must wait, and the implementation is an external command

If you choose the wrong one, the API may still look plausible, but the runtime behavior will be wrong.

