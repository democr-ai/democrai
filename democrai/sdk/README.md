# Democrai SDK

`democrai.sdk` is the public extension surface consumed by modules, engines and
extractors. It lives in the same Python package as `democrai.core`, but it has a
different boundary: SDK symbols are public contracts; core symbols are internal
implementation.

Preferred import:

```python
from democrai.sdk import ...
```

## Boundary

Allowed for extensions:

- `democrai.sdk`
- SDK subdomains such as `democrai.sdk.database`, `democrai.sdk.engines`,
  `democrai.sdk.extractors`, `democrai.sdk.tasks` and `democrai.sdk.ui`
- components and helpers exported by the SDK

Not allowed:

- `democrai.core`
- desktop/web clients
- direct access to providers, sessions, runtimes or internal registries

The fact that the SDK may import core internally does not make those core
symbols public.

## Key Files

- `client.py`: SDK object bound to module/runtime context.
- `database.py`: scoped module persistence.
- `ui.py`, `effects.py`, `pages.py`: UI builder, effects and client messages.
- `decorators.py`, `module_decorators.py`: action, page, hook and command
  registration.
- `tasks.py`: tasks, persisted progress and progress streams.
- `media.py`: public media access for modules.
- `knowledge.py`: knowledge ingestion and retrieval APIs.
- `ai.py`, `ai_constants.py`: AI access and public constants.
- `engines.py`: base contracts for engine implementations.
- `extractors.py`: base contracts for extractor implementations.
- `dependencies.py`: dependency helpers used by engines and extractors.

## Modules

Modules use the SDK for:

- action and page registration.
- scoped database access.
- tasks and progress.
- media and knowledge.
- AI provider/objective access.
- UI builder and effects.

Modules must not import core to reach the database, router, session or task
manager. If a capability is missing, add it to the SDK instead of bypassing the
boundary.

## Engines

Engines implement SDK contracts such as base engine/provider classes and
response types. Registration happens through manifests and runtime paths, not by
direct core imports.

Engine manifests declare access, runtime methods, dependencies and model source
behavior. Engine code must not call core registries or runtime internals.

## Extractors

Extractors use SDK extractor contracts and declare access/dependencies in their
manifest. Core discovers and invokes them through the extractor runtime.

## Stability

This package must remain importable after `pip install democrai`. Changes to SDK
contracts must consider:

- compatibility with existing modules.
- compatibility with external engines and extractors.
- public documentation.
- import-boundary tests.

## Rules

- Do not expose core symbols for convenience unless they are intended to become
  public contracts.
- Do not make modules, engines or extractors import `democrai.core`.
- Prefer small explicit facades over leaking runtime internals.
- Every new SDK method needs clear ownership, inputs, outputs and error
  behavior.
