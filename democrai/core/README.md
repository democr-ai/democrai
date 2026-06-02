# Democrai Core

`democrai.core` is the internal application runtime. It owns bootstrap,
configuration, storage, networking, request handling, registries, sandboxing,
background tasks, AI orchestration and knowledge services.

It is not a public extension API. Modules, engines and extractors must import
from `democrai.sdk`, not from `democrai.core`.

## Boundary

Public extension boundary:

```python
from democrai.sdk import ...
```

Blocked extension boundary:

```python
from democrai.core import ...
```

The module/engine/extractor registration paths enforce this direction. Core can
call extension code through registries, manifests and SDK-facing contracts, but
extension code must not depend on core internals.

## Bootstrap

The local runner builds `CoreRuntimeOptions` and calls:

```python
democrai.core.runtime.entrypoint.start_core_runtime(...)
```

Core receives:

- `mode`: `desktop` or `server`
- HTTP settings
- runtime module paths
- runtime engine paths
- runtime extractor paths

Runtime paths come from:

```bash
DEMOCRAI_MODULES_PATH
DEMOCRAI_ENGINES_PATH
DEMOCRAI_EXTRACTORS_PATH
```

Core normalizes these paths and uses them for discovery and runtime
registration. It does not assume extensions live next to the installed package.

## Runtime Modes

`server` mode starts the HTTP/WebSocket runtime.

`desktop` mode starts core for desktop use. Without `--http`, HTTP is limited to
the media proxy surface expected by the desktop client. With `--http`, the full
HTTP/WebSocket runtime is also exposed.

The desktop client is not part of core. The external runner decides whether to
launch `clients/qtdesktop` or a web client.

## Main Areas

- `application`: business services, request cycle, routing, sessions, auth,
  tasks, AI orchestration, knowledge and setup.
- `infrastructure`: database, storage, network, module loading, sandbox and
  runtime adapters.
- `platform`: shared internal platform utilities, UI builder/runtime,
  workflow/agent helpers and configuration helpers.
- `runtime`: bootstrap pipeline, CLI handling, dependency environment,
  process lifecycle and app context.

## Storage

Core uses separated storage domains:

- core database: users, roles, preferences, registry, sessions and internal
  runtime state.
- data storage: application/module data, including module-owned models and
  migrations.
- media storage: uploaded/generated media.
- vector storage: embeddings and vector indices.
- KG storage: graph nodes, edges and evidence.
- observability storage: events, audits, runtime metrics and model usage.

Each domain has its own provider/factory/migration flow where needed.

## Modules

Modules are runtime extensions discovered from `DEMOCRAI_MODULES_PATH`.

Rules:

- import only `democrai.sdk`
- define UI structure in YAML when building module UI
- keep module migrations inside the module
- do not import core, desktop clients or web clients
- declare access requirements through manifests/contracts, not ad hoc runtime
  bypasses

Module migrations are executed by core, but owned by the module folder.

## Engines

Engines are runtime extensions discovered from `DEMOCRAI_ENGINES_PATH`.

Core reads engine manifests, syncs registry metadata and starts isolated engine
workers for active runtime instances. Engine runtime processes are keyed by
engine registry rows so heavy models can be reused by multiple callers.

Engine code must use `democrai.sdk.engines` and related SDK helpers. Runtime
access, environment variables, allowed imports and subprocess permissions are
declared in the engine manifest.

## Extractors

Extractors are runtime extensions discovered from `DEMOCRAI_EXTRACTORS_PATH`.

Core reads extractor manifests, syncs registry metadata and starts extractor
runtime workers when needed by knowledge/media processing.

Extractor code must use SDK contracts and avoid core imports.

## Sandbox

Core has two sandbox layers:

- Python-level policy guards for filesystem, subprocess and network calls.
- Optional Linux OS-level network egress enforcement through a privileged helper.

The helper is intentionally small and runs outside the application sandbox. It
receives only socket/policy paths and parent process information. It does not
read app configuration, database approvals or extension code.

## Packaging

`democrai.core` is packaged with `democrai.sdk` because both are part of the
installable `democrai` package. The package install should make SDK imports
available to developers while keeping core as an internal implementation detail.

Extension roots and clients are runtime inputs and are not required for:

```python
from democrai.sdk import ...
```
