# Installation And Runtime

This section covers the methods you use when a module needs to request extractor installation, synchronize the live extractor runtime after lifecycle changes, or check whether an extractor is ready on the current node.

These methods are intended for setup screens, admin tools, and extractor activation flows. They mirror the engine lifecycle shape while staying in the extractor domain.

## `request_install(extractor_id: str, force: bool = False, install_config: dict | None = None, requested_by: dict | None = None, task_id: str | None = None)`

This method publishes an extractor installation request event and returns the event payload that was emitted.

Example:

```python
install_event = await module_sdk.extractors.request_install(
    extractor_id="docling",
    force=False,
    install_config={
        "ocr_engine": "rapidocr",
    },
    requested_by={
        "user_id": 42,
        "organization_id": 7,
    },
    task_id=task_id,
)
```

### What It Is For

Use `request_install(...)` when your module wants to start the official extractor installation flow rather than directly running install logic itself.

This method does not mean "install the extractor inside this action". It means "publish an `extractor.install.requested` event and let the runtime install pipeline process it".

That distinction matters because extractor installation is multinode runtime work. Each node that consumes the event can install and check its own local dependencies while recording node-level install status.

### What It Does

Under the hood, the method delegates to `publish_extractor_install_requested(...)`.

That flow:

1. builds a normalized install event
2. includes manifest and version metadata
3. records the source runtime node
4. updates `ExtractorRegistry` rows to `installing` when appropriate
5. records source-node install status
6. broadcasts the event on the extractor install stream
7. returns the event payload to the caller

The returned payload includes fields such as:

- `event_id`
- `event_name`
- `extractor_id`
- `manifest_version`
- `extractor_version`
- `force`
- `install_config`
- `source_node_id`
- `requested_by`
- `task_id`
- `requested_at`

### Install Configuration

`install_config` is the pre-install configuration selected by the user before
the install request is published. It is different from runtime extractor config.

Use it for choices that affect what the installer downloads or prepares, such
as OCR backends or model artifacts. Runtime behavior that can be changed after
installation belongs in the extractor registry config instead.

The install event carries `install_config` so background installers and node
install status records can reconstruct the same request. Do not store
pre-install choices only in UI state.

### Background Task Attachment

Pass `task_id` when the request is launched from a background task and the
installer should stream progress/output into that task.

This is the same pattern used by engine installation: the action creates the
background task, passes its id to the SDK method, and the UI attaches a
`BackgroundTask` component to that id.

### When To Use `force`

Pass `force=True` only when the module is explicitly asking the runtime to reinstall or refresh the extractor even if it may already look ready.

In normal interactive installs, `force=False` is usually the correct default.

### When To Use `requested_by`

Use `requested_by` when you want the installation event to retain user and organization context for auditability, debugging, or admin workflows.

## `sync_runtime() -> None`

This method tells the runtime extractor manager to synchronize the currently active extractors.

Example:

```python
await module_sdk.extractors.sync_runtime()
```

Use `sync_runtime()` after a module changes extractor lifecycle state in a way that should be reflected in the live runtime manager.

Typical examples:

- after activating an extractor
- after deactivating an extractor
- after a configuration change that affects active extractor handles

Updating the database or UI is not enough. The runtime manager keeps active extractor handles, and those handles need to be brought back in sync with persisted extractor state.

## `check_ready(extractor_id: str) -> dict`

This method checks whether an extractor runtime is installed and importable on the current node.

Example:

```python
ready = await module_sdk.extractors.check_ready(extractor_id="docling")

if not ready.get("ready"):
    missing = list(ready.get("missing_local") or [])
```

### What It Is For

Use `check_ready(...)` before activation when the UI needs to decide whether the extractor can be loaded now or whether an installation step is still needed.

This method answers a different question from resolution and extraction:

- `resolve(...)` decides which configured MIME binding should handle a file.
- `check_ready(...)` checks whether an extractor's runtime dependencies are present.
- `extract(...)` executes the resolved extractor.

### Return Value

The current readiness payload uses these fields:

- `ready`: whether the extractor runtime is available
- `missing_local`: extractor-local dependencies that are missing
- `message`: human-readable readiness message

Activation flows can use `missing_local` and `message` to decide whether to show an install prompt instead of trying to instantiate the extractor.

## Typical Extractor Lifecycle Flow

A realistic module flow often looks like this:

1. list manifests or registered extractor rows
2. check whether the extractor runtime is ready with `check_ready(...)`
3. request installation if dependencies are missing
4. activate or update the extractor registry row
5. call `sync_runtime()`
6. configure MIME bindings with `set_mime_type_binding(...)`
7. resolve and run extraction with `resolve(...)` or `extract(...)`

This ordering keeps discovery, installation, activation, and execution as separate concerns.
