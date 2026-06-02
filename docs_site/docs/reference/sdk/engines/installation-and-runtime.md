# Installation And Runtime

This section covers the methods you use when a module needs to trigger engine installation, inspect per-node install state, activate or deactivate an engine instance, or validate whether a provider configuration is ready to run.

These methods are especially important in admin screens, setup flows, and engine activation UI.

## Lifecycle Boundary

Engine lifecycle state is owned by `sdk.engines`, not by generic model CRUD.

Module code can use `module_sdk.models.engine_registry` to create rows, read rows, and update configuration fields. It should not set lifecycle statuses such as `installing`, `installed`, or `active` directly through `engine_registry.update(...)`.

Use these methods instead:

- `begin_install(engine_registry_id=...)`
- `install_status(engine_registry_id=...)`
- `activation_requirements(engine_registry_id=...)`
- `activate_instance(engine_registry_id=...)`
- `deactivate_instance(engine_registry_id=...)`

The core runtime owns the database status transition, runtime synchronization, and multinode install aggregation behind those methods.

## `begin_install(engine_registry_id: int, force: bool = False, requested_by: dict | None = None, task_id: str | None = None) -> dict`

This method starts the official install request for a configured engine registry row.

Example:

```python
result = await module_sdk.engines.begin_install(
    engine_registry_id=42,
    force=False,
    requested_by={
        "user_id": 42,
        "organization_id": 7,
    },
    task_id="task-123",
)
```

### What It Is For

Use `begin_install(...)` from module UI and setup flows when the user is installing a configured engine instance.

The method validates the registry row, resolves its provider, publishes an install request, and returns the current install status payload. The actual installation work is processed by the engine install runtime, not by the action that called the method.

### What It Returns

The return payload includes:

- `engine_registry_id`
- `provider`
- `event`
- `status`

The `status` field contains the aggregated install status with `nodes` and `summary`.

The exact node list depends on the runtime topology. In multinode deployments, the global engine status is derived from per-node install rows rather than from a single local check.

## `install_status(engine_registry_id: int) -> dict`

This method returns the aggregated install status for a configured engine registry row.

Example:

```python
status = await module_sdk.engines.install_status(engine_registry_id=42)
```

Typical payload:

```python
{
    "engine_id": "vllm",
    "status": "installing",
    "supported": True,
    "nodes": [
        {
            "node_id": "node-a",
            "status": "installed",
            "last_event_id": "...",
            "last_error": "",
        },
        {
            "node_id": "node-b",
            "status": "installing",
            "last_event_id": "...",
            "last_error": "",
        },
    ],
    "summary": {
        "pending": 0,
        "installing": 1,
        "installed": 1,
        "error": 0,
    },
}
```

Use this payload for UI state such as "install in progress", node progress tables, and task polling. Do not derive authoritative install state from console output text.

## `request_install(engine_id: str, force: bool = False, requested_by: dict | None = None, task_id: str | None = None)`

This method publishes a provider-level engine installation request event and returns the event payload that was emitted.

Example:

```python
install_event = await module_sdk.engines.request_install(
    engine_id="ollama",
    force=False,
    requested_by={
        "user_id": 42,
        "organization_id": 7,
    },
    task_id=task_id,
)
```

### What It Is For

Use `request_install(...)` only when your code is working at provider/event level and does not have a configured `engine_registry` row.

For module UI flows that install a configured engine instance, prefer `begin_install(engine_registry_id=...)`.

That distinction is important.

This method does not mean "install the engine right now in this action". It means "publish an engine.install.requested event through the runtime and let the install pipeline process it".

This is the correct abstraction for user-facing install actions because installation is a runtime concern, not just a UI button side effect.

### What It Does

Under the hood, the method delegates to `publish_engine_install_requested(...)`.

That flow:

1. builds a normalized install event
2. includes manifest and version metadata
3. records the source runtime node
4. broadcasts the event on the engine install stream
5. returns the event payload to the caller

The returned payload includes fields such as:

- `event_id`
- `event_name`
- `engine_id`
- `manifest_version`
- `engine_version`
- `force`
- `source_node_id`
- `requested_by`
- `requested_at`

### Why You Should Use It

If you bypass this method and call low-level install code directly from a module action, you lose the runtime event model and you make install orchestration harder to observe.

The event-based flow gives the platform a single install entry point that can be tracked across nodes, tasks, registries, and background progress UI.

### Real Usage Pattern

For configured instances, a module should call `begin_install(...)`, capture the returned `event_id`, and drive UI feedback from task progress plus `install_status(...)`.

### Engine Install Artifacts

If an engine installation needs a model-like artifact, such as a tokenizer or
runtime asset, the engine must download it through the SDK media domain and let
the media provider persist it.

Use:

```python
storage_ref = sdk.media.add_model_from_source(
    "qwen3-tts-tokenizer-12hz",
    source={
        "type": "huggingface",
        "repo": "Qwen/Qwen3-TTS-Tokenizer-12Hz",
        "snapshot": True,
    },
)
```

For long downloads, pass a progress callback from the surrounding background
task. The callback receives the current remote filename, bytes downloaded, total
bytes when known, and file index for snapshots. It should only translate that
information into task progress; it should not implement Hugging Face logic in
the engine or module.

Do not call `huggingface_hub.snapshot_download(...)`, write into user-home cache
directories, or materialize final model paths outside the media provider.

When the install flow needs to store the resulting reference in the engine
registry, return it as a config update from the engine install method:

```python
return {
    "config_updates": {
        "tokenizer_path": storage_ref,
        "tokenizer_ref": "Qwen/Qwen3-TTS-Tokenizer-12Hz",
    }
}
```

This keeps installation artifacts shared across nodes and keeps sandbox,
credential, and storage behavior centralized.

### When To Use `force`

Pass `force=True` only when the module is explicitly asking the runtime to reinstall or refresh the engine even if it may already look ready.

In normal interactive installs, `force=False` is usually the correct default.

### When To Use `requested_by`

Use `requested_by` when you want the installation event to retain user and organization context.

That is useful for:

- auditability
- debugging
- admin workflows
- multi-tenant environments where install actions should remain attributable

## `activation_requirements(engine_registry_id: int) -> dict`

This method returns the server-derived requirements for activating a configured engine instance.

Example:

```python
requirements = await module_sdk.engines.activation_requirements(
    engine_registry_id=42
)
```

Typical payload:

```python
{
    "ready": False,
    "reason": "missing_dependencies",
    "engine_registry_id": 42,
    "provider": "vllm",
    "provider_label": "vLLM",
    "supported": True,
    "requires_config": False,
    "missing_dependencies": [
        {"dependency_key": "vllm", "label": "vllm"}
    ],
    "activation_message": "",
}
```

Use this payload to decide what the UI should show:

- open a configuration modal when `reason == "missing_config"`
- open an install approval modal when `missing_dependencies` is not empty
- show an error when the provider is not supported
- call `activate_instance(...)` only when the requirements are ready

The dependency list must be derived server-side. Do not accept a client-provided dependency list when granting install approvals.

## `activate_instance(engine_registry_id: int) -> dict`

This method activates a configured engine instance.

Example:

```python
activation = await module_sdk.engines.activate_instance(
    engine_registry_id=42
)
```

When activation succeeds, the core updates the registry status to `active`, marks the row supported, synchronizes the live runtime, and returns the resulting status payload.

Typical success payload:

```python
{
    "ready": True,
    "engine_registry_id": 42,
    "provider": "vllm",
    "status": "active",
    "supported": True,
    "activation_ready": True,
    "activation_message": "",
}
```

If activation requirements are not satisfied, the method returns `ready=False` and does not modify the registry.

## `deactivate_instance(engine_registry_id: int) -> dict`

This method deactivates a configured engine instance.

Example:

```python
deactivation = await module_sdk.engines.deactivate_instance(
    engine_registry_id=42
)
```

When deactivation succeeds, the core updates the registry status to `installed`, synchronizes the live runtime, and returns the resulting status payload.

## `sync_runtime() -> None`

This method tells the runtime engine manager to synchronize lifecycle state.

Example:

```python
await module_sdk.engines.sync_runtime()
```

### What It Is For

`sync_runtime()` is a low-level synchronization helper.

Do not call it from module lifecycle actions after setting engine status directly. Activation and deactivation should go through `activate_instance(...)` and `deactivate_instance(...)`; those methods perform runtime synchronization internally.

Use `sync_runtime()` only when you are implementing an SDK/core-level lifecycle operation or another approved engine-domain path that already owns the state transition.

### Why It Exists

Updating the database or the UI is not enough. The runtime manager keeps its own loaded engine handles, and those handles need to be brought back in sync with persisted engine state.

`sync_runtime()` does not preload active engines. Provider resolution through
`sdk.ai.get_provider_by_model_registry_id(...)` is also lazy: it returns a
provider handle without loading the model. Engines are loaded by explicit warmup
calls such as `sdk.ai.warmup_provider(provider, wait=True|False)` or by the
first real provider/runtime invocation.

Without a sync step, your module could create a mismatch between:

- what the registry says
- what the UI says
- what the runtime still has loaded

## `list_loaded_models(engine_registry_id: int | str | None = None) -> list[dict]`

This method returns the engine runtime instances currently loaded in memory.

Example:

```python
loaded = await module_sdk.engines.list_loaded_models()
```

To inspect only one configured engine instance:

```python
loaded = await module_sdk.engines.list_loaded_models(engine_registry_id=42)
```

Each row includes runtime identity such as `engine_row_id`, `engine_id`, `status`,
`pid`, and the runtime `model`/`model_path`. When the runtime was started from a
registered model, the row also includes `model_registry_id`, `model_registry_name`,
and `model_display_name`.

Use this for administrative UI that needs to show what is actually resident in the
runtime, not for provider selection. Provider selection should still go through
`sdk.ai` or the model registry APIs.

## `unload_loaded_model(engine_registry_id: int | str, model_registry_id: int | str) -> dict`

This method unloads one loaded model runtime instance from memory.

Example:

```python
result = await module_sdk.engines.unload_loaded_model(
    engine_registry_id=42,
    model_registry_id=128,
)
```

The return payload has:

- `status`: currently `ok`
- `unloaded`: `true` when a loaded runtime handle existed and was closed

This does not deactivate the engine registry row and does not deactivate any
`model_registry` row. It only releases the live runtime handle for the selected
engine/model pair. A later provider request can load it again.

## `stop_engine(engine_registry_id: int | str) -> dict`

This method stops all loaded model runtime instances for one configured engine
row.

Example:

```python
result = await module_sdk.engines.stop_engine(engine_registry_id=42)
```

The return payload has:

- `status`: currently `ok`
- `stopped`: `true` when the runtime accepted the stop request

Use this for runtime administration screens that need to release all live
handles for one engine instance. It does not delete the engine registry row and
does not remove registered model bindings.

## `list_active_jobs() -> list[dict]`

This method returns active engine orchestrator jobs.

Example:

```python
jobs = await module_sdk.engines.list_active_jobs()
```

Use this for admin/runtime views that need to show queued, resolving, loading,
streaming, batching, cancelling, or erroring work handled by the engine
orchestrator.

When the separate engine orchestrator process is active, the data comes from the
orchestrator status endpoint. When the runtime is using the in-process fallback,
the method currently returns an empty list.

## `check_runtime_config(engine_id: str, config: dict | None = None) -> dict`

This method validates a provider configuration against the engine runtime and returns the validation payload.

Example:

```python
status = await module_sdk.engines.check_runtime_config(
    engine_id="openai",
    config={"api_key": "..."},
)
```

### What It Is For

Use this before activation, before enabling a "Save and activate" button, or when you want to explain to the user why an engine configuration is not ready.

This method answers the question:

"Given this engine id and this config payload, is the runtime willing to consider the engine ready?"

### What It Actually Does

The runtime loads the engine class and invokes its local validation method under the engine runtime safety context. Concretely, the method delegates to `check_engine_runtime_config(...)`, which in turn asks the engine runtime to call the engine class method `_validate_config_local(...)`.

That means the validation logic is engine-defined.

The SDK does not invent generic rules such as "if there is a key called api_key then it is ready". Instead, it lets the engine implementation decide.

### Return Value

The exact payload depends on the engine implementation, but the current module flows typically expect fields like:

- `ready`
- `message`

The `system` module uses this result to drive activation readiness UI and to surface a human-readable message when activation is blocked.

### Real Usage Pattern

In the engine instance page, the `system` module does exactly this:

1. load the engine row
2. read the persisted config
3. call `check_runtime_config(...)`
4. use the returned `ready` and `message` fields to decide whether activation should be allowed

That is the correct mental model for this method. It is not a generic JSON schema validator. It is a runtime readiness check.

### Why This Method Matters

A provider can be:

- supported by the machine
- installed correctly
- still not activation-ready because the runtime config is incomplete or invalid

`is_supported(...)` and `request_install(...)` do not answer that question. `check_runtime_config(...)` does.

## `check_ready(engine_id: str) -> dict`

This method checks whether an engine runtime is installed and importable.

Example:

```python
ready = await module_sdk.engines.check_ready(engine_id="vllm")

if not ready.get("ready"):
    missing = [
        *list(ready.get("missing_shared") or []),
        *list(ready.get("missing_local") or []),
    ]
```

### What It Is For

Use `check_ready(...)` for low-level local readiness checks when you are working with provider/runtime code.

For module activation UI, prefer `activation_requirements(engine_registry_id=...)`. It wraps provider support, required config, and runtime readiness into the shape the UI needs.

This method answers a different question from the nearby runtime helpers:

- `is_supported(...)` checks whether the current machine can support the engine.
- `check_ready(...)` checks whether the engine runtime dependencies are present.
- `check_runtime_config(...)` validates the provider configuration payload.

### Return Value

The current runtime readiness payload uses these fields:

- `ready`: whether the engine runtime is available
- `missing_shared`: shared dependencies that are missing
- `missing_local`: engine-local dependencies that are missing

Activation flows can use the missing dependency lists to decide whether to show an
install prompt instead of trying to instantiate the engine.

## `evaluate_model_resources(model_registry_id: int | str, context_length: int, runtime_overrides: dict | None = None) -> dict`

This method estimates the runtime resources required by one registered model at
the requested context length.

Example:

```python
resources = await module_sdk.engines.evaluate_model_resources(
    model_registry_id=128,
    context_length=8192,
    runtime_overrides={"gpu_layers": 32},
)
```

Use this when an engine/model configuration UI needs server-derived resource
information before saving or running a model. The SDK delegates the estimate to
the engine resource evaluator for the registered model; module code should not
reimplement VRAM/RAM formulas locally.

## Typical Engine Lifecycle Flow

A realistic module flow usually looks like this:

1. list or resolve the provider definition
2. read `provider_requirements(...)`
3. create or update the `engine_registry` config row
4. call `activation_requirements(...)`
5. request installation with `begin_install(...)` if dependencies are missing
6. activate with `activate_instance(...)` when requirements are ready
7. deactivate with `deactivate_instance(...)` when the user disables the engine

This ordering matters because each method answers a different operational question.
