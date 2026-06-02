# Engines

External AI engines live here during repository-local development. At runtime
the runner passes this directory, or another configured directory, through
`DEMOCRAI_ENGINES_PATH`.

Engines are not part of the `democrai` package by default. They are runtime
extensions discovered from configured paths.

## Boundary

Engine implementations must import SDK contracts:

```python
from democrai.sdk.engines import BaseEngine, LLMProvider
```

They must not import from `democrai.core`. Core discovers engines through
manifest metadata and invokes them through the engine runtime boundary.

## Layout

Current layout:

- `engines/_schemas`: shared JSON schemas for model definitions and catalogs.
- `engines/<engine>/manifest.json`: engine metadata, provider contract,
  dependency declarations, runtime methods and sandbox access.
- `engines/<engine>/engine.py`: implementation entrypoint referenced by the
  manifest.
- `engines/<engine>/assets`: icons and engine-owned assets.
- `engines/<engine>/models/catalog.json`: static catalog when the engine owns
  one or participates in inventory import flows.
- `engines/<engine>/models/schemas/add_model.json`: schema for JSON-defined
  custom models when supported.
- `engines/<engine>/models/schemas/upload_model.json`: schema for artifact
  uploads when supported.
- `engines/tests`: isolated baseline and runtime tests for specific engines.

## Manifest Contract

Each `manifest.json` declares:

- `id`, `name`, `kind`
- `entrypoint`, for example `engines.onnx.engine:OnnxEngine`
- install/runtime environment variables
- install/runtime sandbox access
- allowed dynamic imports or subprocess commands
- provider metadata and runtime methods
- dependency metadata and configuration schema
- model source behavior

The `provider.model_source` field declares where available models come from:

- `inventory`: the engine consumes models already present in the model
  inventory.
- `engine_catalog`: the engine owns a catalog and may have engine-specific model
  download or management behavior.
- `provider_api`: the configured provider instance lists models through its
  API.

If `model_source` is `provider_api`, model listing must use the provider API for
the configured instance. Do not fall back to a static catalog.

The older `models.source_modes` block (`catalog`, `definition`, `artifact`) is
legacy metadata for catalog/import flows. It is not the engine instance
model-picker contract.

## Runtime

Runtime engine instances run in subprocesses owned by core's engine runtime.
The subprocess is keyed by the engine registry row, so calls to the same active
engine/model reuse the same process instead of creating one process per module.

This is intentional for heavy runtimes such as vLLM, ONNX, MLX or llama.cpp,
where multiple processes would duplicate model memory, native runtimes and
startup cost.

The engine worker sandbox is engine-scoped, not module-scoped:

- declare only access required by the engine itself in the engine manifest
- do not grant module-specific filesystem or network access to a shared engine
  worker
- do not pass raw module-owned paths into the worker unless they are first
  authorized and materialized by the parent application/runtime

If a future feature needs module-specific access, keep that access in the
parent/module/core boundary and send the engine worker only primitive values or
materialized engine-owned inputs.

## Installation

Installation is engine-owned but orchestrated by core.

Important rules:

- declare Python dependencies in the manifest and engine implementation
- keep install-time environment under engine-specific cache/config paths
- use manifest access declarations for filesystem and network openings
- stream verbose install output as task progress stream events
- reserve persisted task progress updates for phase changes and final status

Engine installation must not rely on private host paths, local package leakage
or undeclared native tools.

## Support Baseline

An engine manifest may declare preliminary compatibility, such as operating
system, architecture, GPU or driver requirements. That declaration is not proof
that the engine is actually supported on the current machine.

Before an engine is considered effectively supported on a system, its
installation and a minimal model/runtime test must pass in an environment that
is independent from Democrai.

That external baseline is part of the engine validation flow:

- create a clean environment outside the Democrai engine runtime
- install the same engine dependencies without Democrai-specific toolchain,
  path, environment or sandbox workarounds
- run the same kind of model/runtime operation that Democrai will execute

If the external baseline fails because the operating system, compiler, driver,
hardware or native library stack cannot run the engine, the engine is not
supported on that system. Do not add hardcoded host-specific workarounds in
Democrai to make the baseline pass.

Do not use preliminary compatibility checks as a hard install gate unless the
engine declares an explicit incompatibility, such as an unsupported operating
system. Engines that are compatible on paper but fail during dependency
installation, native compilation, model loading or runtime execution must be
marked unsupported from that observed failure.

If the external baseline passes, the same flow must pass through Democrai:
engine installation, model availability/download, engine activation, model
binding activation and model test. Any Democrai failure after a passing baseline
is a Democrai integration issue, usually in engine env isolation, dependency
resolution, sandbox access or model materialization.

Sandbox openings are not workarounds when they are required by the engine and
declared in the engine manifest with the narrowest practical scope. Host-specific
compiler selection, environment flags, private paths or local package leakage
are not acceptable compatibility mechanisms.
