# Runtime Identity and Logging

This section covers the five direct helper methods on `module_sdk.system`:

- `os_name()`
- `has_nvidia()`
- `temp_dir()`
- `is_dev()`
- `log(...)`

These are the smallest methods in the domain, but they are useful precisely because they let module code ask simple runtime questions without reaching into core internals.

## `os_name() -> str`

This method returns the normalized operating system name of the current runtime.

Example:

```python
current_os = module_sdk.system.os_name()
```

Typical values are:

- `linux`
- `darwin`
- `windows`

### What It Is For

Use it when module behavior genuinely depends on the current host OS.

Typical examples:

- deciding whether to show a platform-specific warning
- selecting an engine/provider flow that only makes sense on one platform
- avoiding a feature path that is unsupported on the current OS

### What It Actually Does

The method delegates to the module-level helper `sdk.system.os_name()`, which wraps `platform.system()` and lowercases the result.

That means it is intentionally simple and has no application-specific logic layered on top.

## `has_nvidia() -> bool`

This method returns whether the current runtime reports an NVIDIA GPU.

Example:

```python
if module_sdk.system.has_nvidia():
    module_sdk.system.log("NVIDIA GPU detected")
```

### What It Is For

Use it when your module needs to branch on GPU availability, especially for engine-related or media-processing flows where NVIDIA support matters.

### What It Actually Does

The method delegates to the module-level helper `sdk.system.has_nvidia()`, which:

1. asks the resource monitor for a current resource snapshot
2. returns `False` if resource detection itself fails
3. otherwise returns the truthiness of `has_nvidia_gpu`

That means this is a best-effort runtime capability check, not a hardware inventory API.

## `temp_dir() -> str`

This method returns the application temporary directory path:

```python
work_root = module_sdk.system.temp_dir()
```

The returned directory is:

- located under the application data directory as `tmp`
- created if it does not already exist
- part of the runtime paths available to guarded module tasks

Use it when a module needs a temporary staging directory for files that must stay inside the application runtime area. For example, a model import flow can create a per-operation subdirectory under this path, write downloaded files there, persist them through `module_sdk.media`, and then remove the staging directory.

Do not use this as permanent storage. Persist final artifacts through the appropriate SDK domain, such as `module_sdk.media`.

## `is_dev() -> bool`

This method returns whether the application runtime is running in development
mode.

Example:

```python
if module_sdk.system.is_dev():
    module_sdk.system.log("Development-only diagnostics enabled")
```

Use it for development-only diagnostics or admin UI affordances. Do not use it
to define domain behavior that must differ between production and development
without an explicit application contract.

## `log(message, level="info") -> None`

This method writes a log line through the application logger using the current module name as a stable prefix.

Example:

```python
module_sdk.system.log("Starting synchronization")
module_sdk.system.log("Upload failed", "error")
```

### What It Is For

Use it whenever module code needs to log something operationally relevant and you want the message to be clearly attributable to the module.

This is the common pattern in the existing modules:

- authentication flows log login attempts and failures
- setup flows log major setup steps
- system actions log operational errors
- component flows log UI/runtime errors

### What It Actually Does

The method:

1. builds a prefix like `[your_module_name]`
2. resolves `app_ctx().logger`
3. if no logger exists, returns without raising
4. otherwise calls the logger method named by `level`
5. if that level method does not exist, falls back to `logger.info`

The actual logger call is made with:

- the prefixed message
- the current module name as the logger category/domain argument

### Important Behavior

This method is deliberately forgiving:

- if the logger is missing, it silently does nothing
- if the level is unknown, it falls back to `info`

So it is safe for normal module logging, but you should not mistake it for a guaranteed audit or persistence channel.

Telemetry and audit persistence are not exposed through `module_sdk.system`. Use `log(...)` for operational log lines only; audit and model-usage records are emitted by the core runtime.

## Practical Guidance

Use these helpers when you need small pieces of runtime awareness.

Do not build heavy runtime decision logic around them unless the check is genuinely the correct source of truth. For example, `has_nvidia()` is good for gating a UI hint, but engine support decisions still belong in the engine/runtime layer.
