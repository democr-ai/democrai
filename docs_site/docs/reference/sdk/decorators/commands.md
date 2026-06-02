# Decorators: Commands

## Command Decorators

The command decorators are for module code that is not a normal UI action and instead belongs to the command runtime.

Use these when the function should be managed according to a lifecycle:

- callable on demand
- scheduled
- long-running
- single-run at startup

## `callable_command(name=None)`

Use this when the command should be invokable on demand through the command runtime.

### What it does

The decorator:

- resolves the module-qualified name
- registers the wrapper in the action/command registry
- registers the command in the module command registry with lifecycle `"callable"`

That means it behaves like a command asset, not like a normal UI action.

### Why use it

Use this when a module exposes an operational command that should be called explicitly rather than scheduled automatically or kept running continuously.

## `scheduled_command(name=None, cron=None, interval_seconds=None)`

Use this when the command should run on a schedule.

### What it does

The decorator registers the function in the module command registry with lifecycle `"schedule"` plus:

- `cron` if provided
- `interval_seconds` if provided

### Why use it

Use this for periodic module work such as:

- cleanup jobs
- periodic sync
- timed maintenance
- poll-style ingestion

### Example

```python
from democrai.sdk.decorators import scheduled_command

@scheduled_command("refresh_index", interval_seconds=300)
def refresh_index():
    ...
```

Use `cron` when the schedule is calendar-shaped. Use `interval_seconds` when it is fixed-interval runtime work.

## `long_run_command(name=None, restart_on_exit=True)`

Use this for commands that should stay alive after boot.

### What it does

The decorator registers the function as a module command with lifecycle `"long_run"` and stores whether it should restart on exit.

### Why use it

Use this when the command is conceptually a long-lived worker, watcher, or background service belonging to the module.

### Real project example

The codebase has module commands declared like this:

```python
from democrai.sdk.decorators import long_run_command

@long_run_command("dashboard_runtime")
def dashboard_runtime():
    ...
```

## `single_run_command(name=None)`

Use this for commands that should execute once during startup and then exit.

### What it does

The decorator registers the function in the module command registry with lifecycle `"single_run"`.

### Why use it

Use this when the command is a one-shot initialization or boot-time task rather than an always-on worker.

## Choosing among command decorators

Use:

- `callable_command` for on-demand commands
- `scheduled_command` for periodic work
- `long_run_command` for persistent runtime processes
- `single_run_command` for boot-time one-shot work

If the user or client is clicking a button in the UI, that is usually an `@action`, not a command.
