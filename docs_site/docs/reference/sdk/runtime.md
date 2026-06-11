# Runtime Lifecycle

`democrai.sdk.runtime` exposes the application runtime boundary used by core
process entrypoints and by supervising launchers.

It is intentionally small:

- `start(...)`
- `stop(...)`
- `spawn_core_worker(...)`
- `release_core_worker(...)`
- `RuntimeHandle`

Use `start(...)` and `stop(...)` when a process needs to start or stop the
Democr.ai core runtime in that same process. Use `spawn_core_worker(...)` and
`release_core_worker(...)` when a supervising process needs to run the core as
a child process. Extension code under `modules/*`, `engines/*`, and
`extractors/*` normally does not call these methods.

The SDK runtime boundary does not launch UI clients. Client process orchestration
belongs to the repository or product launcher.

## `start(...) -> RuntimeHandle`

```python
from democrai.sdk.runtime import start

handle = start(app_dir="/path/to/application")
```

`start(...)` parses runtime arguments, handles runtime CLI commands, configures
extension path environment variables when `app_dir` is provided, and starts the
core runtime in the current process when the selected mode requires it.

The returned `RuntimeHandle` contains:

- `args`: parsed runtime arguments
- `endpoint`: the runtime endpoint exposed by the core when it is started in this process
- `exit_code`: an exit code when the call handled a CLI/helper path and no client should be started

### Arguments

```python
handle = start(
    argv=["--mode", "desktop"],
    app_dir="/path/to/application",
    configure_args=configure_runtime_args,
)
```

- `argv`: optional argument list. When omitted, the current process arguments are used.
- `app_dir`: optional application directory. When provided, missing extension path environment variables are initialized from `modules`, `engines`, and `extractors` under this directory.
- `configure_args`: optional callback called after CLI command handling and before the core runtime starts. A launcher can use it to adjust runtime arguments before the core process starts, for example enabling HTTP when the selected client requires it.

If `handle.exit_code` is not `None`, the caller should return that code and skip client startup.

## `stop(...) -> None`

```python
from democrai.sdk.runtime import stop

stop()
```

`stop(...)` shuts down the active runtime using the core cleanup sequence.

Optional launcher-owned resources can be passed through:

```python
stop(reloader=reloader, child_proc=child_proc)
```

- `reloader`: a launcher-owned reloader object
- `child_proc`: a launcher-owned client process

The handle does not expose the internal core context.

Launcher-owned process state stays outside the SDK. If a product launcher starts
the core and the client as separate processes, it should call `start(...)` only
inside the core process and use an explicit parent/child protocol to pass the
returned endpoint back to the supervising process.

## `spawn_core_worker(...) -> process`

```python
from democrai.sdk.runtime import spawn_core_worker

process = spawn_core_worker(
    command,
    env=worker_env,
    pass_fds=(listener_fd,),
    runtime_mode="server",
)
```

`spawn_core_worker(...)` starts a core worker child process on behalf of a
supervising launcher. It is the supervisor-side entry point for the OS sandbox:
when `sandbox.os.enabled` is set in the master configuration (`config.yaml` in
the data directory), the worker is launched through the platform launch
strategy instead of a plain subprocess.

With the sandbox enabled the call:

- starts the sandbox spawn broker and merges its environment into the worker
  environment, on platforms whose launch strategy uses one
- builds the core worker launch policy (network proxy session, filesystem
  access rules, helper environment)
- spawns the worker through the platform launch strategy

With the sandbox disabled the worker is spawned as a plain subprocess with the
given command, environment, and inherited descriptors.

### Arguments

- `command`: full worker command line. The supervisor owns the command shape,
  including its worker re-entry flags.
- `env`: worker environment. The supervisor owns its launcher protocol
  variables and sets them before the call.
- `pass_fds`: file descriptors the worker inherits, for example a shared
  listener socket in server mode.
- `runtime_mode`: runtime mode string forwarded to the launch policy.

Returns the worker process handle. When a spawn broker was started, it is
attached to the returned handle and stays open for the worker lifetime.

## `release_core_worker(...) -> None`

```python
from democrai.sdk.runtime import release_core_worker

release_core_worker(process)
```

Releases supervisor-side resources attached to a process handle returned by
`spawn_core_worker(...)`, currently the sandbox spawn broker. Call it whenever
the supervisor stops or discards a worker process: shutdown, restart on the
application restart exit code, or kill. It is safe to call on handles without
attached resources and on `None`.

## Core Process Shape

```python
from democrai.sdk.runtime import start, stop


def core_main() -> int:
    handle = start(app_dir="/path/to/application")
    if handle.exit_code is not None:
        return int(handle.exit_code)

    try:
        publish_endpoint_to_parent(handle.endpoint)
        wait_for_shutdown()
        return 0
    finally:
        stop()
```

## Desktop Launcher Shape

Desktop launchers should keep the core and client in separate processes:

```python
from democrai.sdk.runtime import release_core_worker, spawn_core_worker


def launcher_main() -> int:
    core = spawn_core_worker(core_command(), env=core_env())
    endpoint = read_endpoint_from_core(core)
    client = start_client_process(endpoint)

    try:
        return supervise(core, client)
    finally:
        terminate(client)
        release_core_worker(core)
        terminate(core)
```
