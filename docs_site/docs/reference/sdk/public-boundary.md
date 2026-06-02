# Public SDK Boundary

`democrai.sdk` is the public Python boundary for extensions.

Extension code means:

- modules loaded from `DEMOCRAI_MODULES_PATH`
- engines loaded from `DEMOCRAI_ENGINES_PATH`
- extractors loaded from `DEMOCRAI_EXTRACTORS_PATH`

These extensions may import `democrai.sdk`. They must not import
`democrai.core`.

## Import Rule

Use SDK imports:

```python
from democrai.sdk.decorators import action
from democrai.sdk.database import get_module_base
from democrai.sdk.engines import BaseEngine
from democrai.sdk.extractors import BaseExtractor
```

Do not import core from extensions:

```python
from democrai.core.infrastructure.database import SessionLocal
from democrai.core.runtime.foundation.app import app_ctx
```

The runtime registration path blocks `democrai.core` imports in modules. The
same boundary applies architecturally to engines and extractors.

## Why Core And SDK Ship Together

The installable package is `democrai`. It contains both:

- `democrai.sdk`
- `democrai.core`

They ship together so the runtime and public SDK versions stay compatible. That
does not make core public. Core is implementation; SDK is contract.

## What The SDK Owns

Use the SDK for:

- action, page, hook and command registration
- module-owned database tables
- UI builder/effects
- task lifecycle and progress
- media storage and materialization
- AI provider access through runtime contracts
- knowledge ingestion/extraction contracts
- engine/extractor base classes and response types

If an extension needs a runtime capability that is not exposed by the SDK, add a
small SDK facade instead of importing core directly.

Runtime entrypoints may also use `democrai.sdk.runtime.start` and
`democrai.sdk.runtime.stop` to start and stop the core runtime through the public
boundary. These methods are for core process entrypoints, not for modules,
engines, or extractors.

## Packaging Contract

`pip install democrai` should make this work:

```python
from democrai.sdk import SDK
```

The root package exports only the root SDK object and request-scoped SDK
proxies:

- `SDK`
- `active_sdk`
- `current_sdk`

Domain APIs are imported from their domain modules:

```python
from democrai.sdk.decorators import action
from democrai.sdk.database import get_module_base
from democrai.sdk.client import active_sdk as sdk
```

Do not document removed root shortcuts for domains. Use `database` through an
injected or active SDK instance.

The wheel is not expected to include the development repository's `modules`,
`engines`, `extractors` or `clients` folders. Those are runtime extension roots
or independent applications.

Runtime paths are configured outside the package:

```bash
DEMOCRAI_MODULES_PATH=/path/to/modules
DEMOCRAI_ENGINES_PATH=/path/to/engines
DEMOCRAI_EXTRACTORS_PATH=/path/to/extractors
```

## Module Persistence

Module-owned data goes through `sdk.database`.

Core-managed entities go through `sdk.models`.

Keep this distinction explicit:

- `sdk.database` -> tables owned by the module.
- `sdk.models` -> entities owned by the runtime.

## UI Boundary

Module UI should be YAML first:

- YAML owns structure, layout, components and binding.
- Python render code loads YAML and seeds data/store.
- action effects mutate surfaces incrementally when possible.

Avoid writing UI contracts in Python just because it is convenient.

## Engine And Extractor Boundary

Engine implementations use `democrai.sdk.engines`.

Extractor implementations use `democrai.sdk.extractors`.

Access, dependencies, runtime methods and model/extractor metadata are declared
in manifests and consumed by core at runtime.
