# SDK Domain: `dependencies`

## Overview

The `dependencies` domain exists for one practical reason: module code sometimes needs an optional dependency, but that dependency is not guaranteed to be available in every runtime context.

In Democr.ai, this is not something modules should handle with ad-hoc `try/except ImportError` blocks scattered around the codebase. Dependency bootstrap is part of the runtime model, and the SDK gives you a supported entry point for that flow.

The first distinction to keep clear is this:

- `module_sdk.dependencies` exposes the facade that module code is expected to use during normal development
- `sdk.dependencies` also reexports a few lower-level helper functions, but those are module-level imports, not methods on the `Dependencies` facade

For most module authors, the method that matters is `module_sdk.dependencies.ensure_import(...)`.

## Mental Model

When you call `ensure_import(...)`, you are not just asking Python to import a module.

You are asking the Democr.ai runtime to make a managed attempt to ensure that module is available in the current dependency environment. In practice, this means the SDK can bootstrap the current engine-scoped dependency environment, retry the import after the engine runtime has checked or installed what it needs, and then raise a structured dependency error if the requirement still cannot be satisfied.

This is important because many optional capabilities are not plain "pip install it once and forget it" dependencies. They can depend on:

- the active engine context
- the engine manifest and readiness checks
- engine-specific install flows
- system-level prerequisites such as external binaries

If you bypass the SDK and write local import fallback logic yourself, you lose that runtime contract and you make your module harder to diagnose when something is missing.

## The Facade Used by Module Code

## `Dependencies`

`Dependencies` is the object exposed through `module_sdk.dependencies`.

It is intentionally small. At the moment, its public surface is just one method:

- `ensure_import(...)`

That small surface is a feature, not a limitation. The goal is to give modules one supported way to request an optional runtime dependency without exposing the entire internal installer layer as the default programming model.

## `ensure_import(module_name: str, dependency_key: str | None = None)`

This is the main method developers should use when a module depends on an optional Python package that may not already be importable in the current runtime context.

### What It Is For

Use `ensure_import(...)` when your module needs to import a package that belongs to a managed runtime capability. Typical examples are AI-related libraries, engine-specific Python packages, or dependencies that may only be installed when a certain engine or feature is actually used.

In other words, you use this method when a normal top-level import would be too rigid.

### Why You Should Use It

The main reason to use `ensure_import(...)` is that it keeps dependency handling aligned with the actual runtime architecture.

If you write code like this:

```python
try:
    import some_optional_package
except ImportError:
    ...
```

you are only checking the current interpreter state. You are not giving the Democr.ai runtime any chance to bootstrap the proper environment, consult engine readiness, or produce a structured error that the rest of the platform understands.

By using `ensure_import(...)`, your module delegates that responsibility to the runtime layer that already knows how dependency installation is supposed to work.

### What It Does Internally

At runtime, `ensure_import(...)` delegates to the central dependency bootstrap flow in `core.runtime.dependencies.ai_bootstrap.ensure_import`.

The important behavior is:

1. it prepares the current engine-scoped dependency environment when needed
2. it tries to import the requested module
3. if the import fails, it resolves the active engine runtime
4. it asks the engine whether it is ready
5. if the engine is not ready, it triggers the engine install flow
6. it bootstraps the environment again and retries the import
7. if the dependency is still unavailable, it raises a structured `DependencyMissingError`

This means the method does substantially more than "import this package for me". It is part of the dependency provisioning contract of the runtime.

### Parameters

#### `module_name`

This is the actual Python module name that should become importable.

Examples:

- `"openai"`
- `"mlx"`
- `"pypdfium2"`
- `"sentence_transformers"`

This is the name passed to `importlib.import_module(...)`, so it must match the module you expect to import in Python code.

#### `dependency_key`

This is an optional logical dependency identifier.

Use it when the dependency should be reported, tracked, or surfaced to the user under a named capability rather than only under the raw import name.

That matters especially when:

- the install contract is defined by a logical key
- the package name and the capability name are not the same thing
- you want runtime errors to refer to the user-facing dependency concept rather than the bare import target

If you omit it, the runtime falls back to the `module_name`.

### Return Value

On success, the method returns the imported Python module object.

That means you can immediately bind it and use it:

```python
pdfium = module_sdk.dependencies.ensure_import(
    "pypdfium2",
    dependency_key="pdf-preview",
)
```

After that, `pdfium` is the imported module, not a wrapper or a boolean status.

### Failure Behavior

If the dependency cannot be made available, the method raises a dependency-related runtime error rather than silently degrading.

This is the correct behavior for this project. The runtime is expected to fail clearly when a required capability is missing instead of pretending the flow succeeded.

Depending on the root cause, the raised error can describe:

- a missing Python dependency
- a missing system dependency required by the install flow
- a missing engine context
- an engine runtime that could not be resolved or installed

From a module-author perspective, the important point is simple: call `ensure_import(...)` when you need the dependency, then write the rest of your code as if the import succeeded. If it does not succeed, let the runtime error surface unless your feature has a very explicit user-facing recovery path.

## Real Usage Pattern

The most common pattern is to call `ensure_import(...)` close to the feature that actually needs the dependency, instead of importing the package unconditionally at module import time.

That keeps startup lighter and avoids making optional features behave like mandatory dependencies.

Example:

```python
def extract_preview_text(file_path: str, module_sdk) -> str:
    pypdfium2 = module_sdk.dependencies.ensure_import(
        "pypdfium2",
        dependency_key="pdf-preview",
    )

    document = pypdfium2.PdfDocument(file_path)
    page = document[0]
    text_page = page.get_textpage()
    return text_page.get_text_range()
```

This pattern is better than a top-level import because the dependency is only requested when the feature actually runs, and the runtime has a chance to provision the environment correctly.

## When To Reach For `dependency_key`

If the dependency name is already obvious and matches the capability the user or runtime cares about, using only `module_name` is often enough:

```python
numpy = module_sdk.dependencies.ensure_import("numpy")
```

Use `dependency_key` when the logical capability matters more than the raw import target:

```python
mlx = module_sdk.dependencies.ensure_import(
    "mlx",
    dependency_key="mlx-engine",
)
```

This is useful when errors, diagnostics, or install flows should refer to the named runtime dependency rather than just the import path.

## What Not To Do

Avoid documenting or implementing dependency handling in modules like this unless you have a very specific reason:

```python
try:
    import pypdfium2
except ImportError:
    return None
```

That pattern is weak for this SDK because:

- it hides the real failure mode
- it bypasses runtime bootstrap
- it makes missing dependencies look like ordinary business logic branches
- it prevents the platform from surfacing a structured dependency error

If the feature genuinely requires the dependency, fail through the managed SDK path instead of introducing a silent fallback.

## Module-Level Helper Functions

Besides the `Dependencies` facade, the `sdk.dependencies` module also reexports a few lower-level helper functions:

- `ensure_import(...)`
- `install_dependency(...)`
- `install_dependencies(...)`
- `install_python_packages(...)`
- `install_torch_runtime(...)`
- `resolve_torch_cuda_profile(...)`
- `resolve_torch_runtime_plan(...)`
- `torch_runtime_matches_plan(...)`
- `write_installed_torch_constraint(...)`
- `install_command_preview(...)`
- `install_system_dependency(...)`
- `is_system_dependency_installed(...)`
- `ensure_engine_venv(...)`
- `ensure_extractor_venv(...)`
- `get_engine_local_cache_path(...)`
- `get_extractor_local_cache_path(...)`
- `fs_path(...)`
- `logical_path(...)`
- `fs_exists(...)`
- `fs_is_dir(...)`
- `fs_is_file(...)`

These are real exports, but they are not methods on `module_sdk.dependencies`.

That distinction matters when you write documentation or examples:

- `module_sdk.dependencies.ensure_import(...)` is valid
- `module_sdk.dependencies.install_dependency(...)` is not part of the facade

### `ensure_import(...)` as a Module-Level Import

This is the same underlying capability exposed by the facade, but imported directly from the module:

```python
from democrai.sdk.dependencies import ensure_import

openai = ensure_import("openai", dependency_key="openai-engine")
```

This can be useful in focused utility code, but for general module authoring the facade access through `module_sdk.dependencies` is usually clearer and more consistent with the rest of the SDK.

### `install_dependency(package: str, force: bool = False)`

This helper installs a single Python package by delegating to the installer layer.

It is a lower-level primitive. It does not express the same high-level intent as `ensure_import(...)`, and it is not the first tool module authors should reach for in normal feature code.

Use it only when you are deliberately building an explicit package installation flow and you know you want to install a concrete package by name.

Example:

```python
from democrai.sdk.dependencies import install_dependency

install_dependency("sentence-transformers")
```

### `install_dependencies(packages: list[str], force: bool = False)`

This is the multi-package variant of the previous helper.

It is useful when you already have an explicit list of Python packages to install and you want to batch them as one installer call.

Example:

```python
from democrai.sdk.dependencies import install_dependencies

install_dependencies([
    "pydub",
    "ffmpeg-python",
])
```

### `install_python_packages(...)`

This is the most configurable low-level installer helper reexported by the module.

It supports details such as:

- explicit module names to verify after installation
- forced reinstall
- custom package indexes
- extra package indexes
- source-install allowance

This function is useful when you are implementing infrastructure-like flows rather than ordinary module business logic.

Example:

```python
from democrai.sdk.dependencies import install_python_packages

install_python_packages(
    ["sentence-transformers"],
    modules=["sentence_transformers"],
    force=False,
)
```

### Torch Runtime Helpers

The module also reexports helpers for the managed Torch runtime plan:

- `install_torch_runtime(...)`
- `resolve_torch_cuda_profile(...)`
- `resolve_torch_runtime_plan(...)`
- `torch_runtime_matches_plan(...)`
- `write_installed_torch_constraint(...)`

These are lower-level helpers for dependency-management and engine-install
flows. They are not methods on `module_sdk.dependencies`.

`resolve_torch_cuda_profile(env=None)` returns the CUDA profile selected from
the runtime environment.

`resolve_torch_runtime_plan(packages=None, modules=None, env=None)` returns the
runtime plan for installing or validating Torch-related packages.

`torch_runtime_matches_plan(packages=None, modules=None, env=None)` checks
whether the current runtime already matches that plan.

`install_torch_runtime(packages=None, modules=None, force=False, env=None,
clean_target=False)` installs the resolved Torch runtime plan through the
managed dependency resolver.

`write_installed_torch_constraint(distributions=("torch",))` writes the
constraint file that records the installed Torch distribution versions.

### `install_command_preview(key: str)`

This helper does not install anything. It returns a human-readable system command preview for a known system dependency key.

At the moment, the supported key is `ffmpeg`.

This is useful when you want to show the user what command would be run on the current operating system before they confirm a system-level installation flow.

Example:

```python
from democrai.sdk.dependencies import install_command_preview

preview = install_command_preview("ffmpeg")
```

In the current codebase this pattern is used by the system dependency-missing modal to explain the expected install command to the user.

### System Dependency Helpers

The module also exports helpers for managed system dependencies:

- `install_system_dependency(key: str)`
- `is_system_dependency_installed(key: str)`

Use these only in explicit dependency-management flows. For normal module
features, prefer `ensure_import(...)` and let the runtime surface missing
dependencies through the managed error path.

### Runtime Environment Helpers

Two helpers ensure isolated runtime environments for installable providers:

- `ensure_engine_venv(engine_id: str, requirements=None)`
- `ensure_extractor_venv(extractor_id: str, requirements=None)`

They are infrastructure helpers for engine/extractor setup flows, not general
module dependency APIs.

### Local Cache and Filesystem Helpers

The module exports cache-path and logical-filesystem helpers:

- `get_engine_local_cache_path(engine_id: str, *parts)`
- `get_extractor_local_cache_path(extractor_id: str, *parts)`
- `fs_path(...)`
- `logical_path(...)`
- `fs_exists(...)`
- `fs_is_dir(...)`
- `fs_is_file(...)`

Use these when provider infrastructure needs the SDK's logical path rules or
engine/extractor-local cache locations. Do not use them to bypass higher-level
SDK domains such as `media` when the value is a persisted user-facing file.

## Which API You Should Normally Choose

For most SDK users, the decision is simple:

- if your code needs an optional runtime dependency before doing work, use `module_sdk.dependencies.ensure_import(...)`
- if you are building dependency-management infrastructure or a dedicated install flow, the module-level helpers from `democrai.sdk.dependencies` may be appropriate

If you are unsure, start with `ensure_import(...)`. It is the safest abstraction for normal module development because it expresses intent in runtime terms: "make this dependency available for the current feature", not "run an installer command right now".
