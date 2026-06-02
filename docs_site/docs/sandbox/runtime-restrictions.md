# Sandbox Runtime Restrictions

## Runtime Guard State

At runtime, the sandbox is not one global boolean. Each guarded execution enters a `process_guard_context(...)` with:

- `subject`: the module, engine, extractor, MCP server, or other runtime subject
- `subject_kind`: the kind of subject, such as `module`, `engine`, `extractor`, `task`, `tool`, `agent`, `pipeline`, or `mcp`
- `allowed_paths`: filesystem roots declared for this subject
- `allowed_targets`: network targets declared for this subject
- `allowed_imports`: sensitive import roots explicitly permitted for this subject
- `allow_subprocess`: whether child process creation is allowed in this phase

`subject` is the concrete runtime actor, such as a module name, engine id, extractor id, or MCP server name. `subject_kind` is its category.

`subject_chain` is the nested execution path. For example, if a module enters another guarded runtime, the chain records both subjects in order. `subject_allow_chain` records the allowlist entries contributed by each subject in that chain. External-access checks use that chain so a nested runtime can be evaluated from the actual guard state, not from a caller-provided flag.

Nested guarded calls merge parent and child allowlists.

`process_guard_context(...)` also activates `network_policy_context(...)`, so filesystem/process restrictions and network policy are normally applied together.

## Filesystem

The filesystem guard permits access only under the active `allowed_paths`, plus runtime paths injected by the framework. Runtime paths include the application runtime directories, standard library paths, package paths, temp paths, and other system read paths needed by Python and common libraries.

The subject-specific entries still matter. They are the entries that say, "this extensible subject is expected to use this path." They are also what external-access checks use when deciding whether a filesystem target is allowed by sandbox policy.

The guard patches common Python filesystem entrypoints, including:

- `open` and `io.open`
- `os.open`, `os.listdir`, `os.stat`, `os.remove`, `os.rename`, and related `os` functions
- `os.path` checks such as `exists`, `isfile`, `getsize`, and `samefile`
- `pathlib.Path` methods such as `read_text`, `write_text`, `iterdir`, `glob`, `unlink`, and `rename`
- `shutil` operations such as `copy`, `copytree`, `move`, `rmtree`, `unpack_archive`, and `make_archive`

If a guarded path is outside the allowed roots, the operation raises `PermissionError` with a sandbox filesystem denial code.

When the path is outside the active filesystem policy, the process guard may also ask the access-policy service whether the path was already approved for the current subject and filesystem operation. That check is synchronous and intentionally cached inside the current guard activation. Low-level filesystem probes do not create pending approval requests automatically; pending filesystem requests must come from explicit SDK or UI flows that know which path and operation the user is trying to approve.

Infrastructure failures during that external-access check are not converted into ordinary sandbox denials. They are logged and surfaced as `sandbox_external_access_check_failed` so operators can distinguish "policy denied this path" from "the approval backend failed".

Use structured filesystem `access` entries when the code must read or write a stable external directory or file. Do not add broad roots such as `/`, `/home`, or a whole project checkout unless the subject truly needs that complete tree.

## Network

The network guard checks outbound targets through the access-policy service.

It patches common Python network entrypoints, including:

- `urllib.request.urlopen`
- `requests.sessions.Session.request`
- `httpx.Client.request` and `httpx.AsyncClient.request`
- `aiohttp.ClientSession._request`
- `socket.connect`, `socket.connect_ex`, `socket.sendto`, and `socket.create_connection`
- `asyncio.open_connection`
- `http.client.HTTPConnection` and `HTTPSConnection`

For each outbound URL or host/port, the guard asks whether the requested network operation is currently allowed for the active subject. Access can be allowed by the active sandbox allowlist, by a session approval, or by a permanent approval. If not, the service can register a pending request and the network operation is denied.

Use structured `access` entries with `resource_type="network"` for stable outbound dependencies that are part of the subject contract. Use the approval flow for user-selected URLs, administrator-selected endpoints, or other targets discovered at runtime.

## Sensitive Imports

The process guard does not block every import. It blocks sensitive import roots that can undermine the Python-level sandbox, currently:

- `ctypes`
- `_ctypes`
- `cffi`
- `_cffi_backend`

If a subject imports one of those roots without declaring it in `allowed_imports`, the import raises `PermissionError`.

Declare `allowed_imports` only when native interop is genuinely required. It is a high-trust signal because those libraries can call outside normal Python APIs.

## Subprocesses

Subprocess execution is blocked by default. The guard wraps:

- `subprocess.Popen`, `run`, `call`, `check_call`, and `check_output`
- `os.system` and `os.popen`
- `os.fork`
- `asyncio.create_subprocess_exec` and `create_subprocess_shell`

The runtime enables `allow_subprocess=True` only in specific phases that need it, such as engine or extractor install flows, and in the SDK task subprocess helper. In install contexts, some file-descriptor based filesystem operations are relaxed because package installers and standard-library cleanup code rely on `dir_fd`-style APIs.

Normal module render and action execution should not start subprocesses directly. If a module needs to run a child process, use the SDK task subprocess helper so the runtime can inject the correct sandbox environment into the child process.

The sandbox environment variables injected for child processes are runtime-owned. Guarded code must not modify `DEMOCRAI_*` variables to spoof identity or policy before spawning a child process. While the process guard is active, mutations through `os.environ`, `os.putenv`, and `os.unsetenv` are denied for `DEMOCRAI_*` names.

## Threads and Blocking Work

The guard state is stored in context variables. To avoid losing that state when code crosses common concurrency boundaries, the process guard wraps thread start and thread-pool submission so the active context is copied into worker threads.

This is why blocking work submitted through the SDK task helpers still sees the same sandbox policy. Directly bypassing those helpers can lose request/session context even if the Python context propagation still carries the low-level guard.

Request identity is preserved when it exists. Interactive user-originated work should carry user, organization, and session into nested runtimes. Long-running or scheduled background work may not have a session; those flows can still create approval requests, but session approval is not valid without an original `session_key`.

## Bypass Context

The core implementation has a `process_guard_bypass_context()` escape hatch for runtime internals that must temporarily perform privileged setup or maintenance work.

Module, engine, and extractor code should not use it. It is not an SDK-level authorization mechanism, and using it would bypass the same policy the module is expected to declare and obey.
