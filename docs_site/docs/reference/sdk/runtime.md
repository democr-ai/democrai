# Runtime Start and Stop

`democrai.sdk.runtime` exposes the application runtime boundary used by core
process entrypoints.

It is intentionally small:

- `start(...)`
- `stop(...)`
- `RuntimeHandle`

Use this boundary when a process needs to start or stop the Democr.ai core
runtime in that same process. Extension code under `modules/*`, `engines/*`,
and `extractors/*` normally does not call these methods.

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
def launcher_main() -> int:
    core = start_core_process(endpoint_pipe=True)
    endpoint = read_endpoint_from_core(core)
    client = start_client_process(endpoint)

    try:
        return supervise(core, client)
    finally:
        terminate(client)
        terminate(core)
```
