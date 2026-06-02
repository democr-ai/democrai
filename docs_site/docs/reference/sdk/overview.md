# SDK Overview

The SDK is the public boundary for modules, engines, and extractors.

If you are writing code under `modules/*`, `engines/*`, or `extractors/*`, import public APIs from `democrai.sdk.*`. The SDK exists to keep extension code stable even when runtime internals, transports, providers, or storage backends change.

## What the SDK Is For

Use the SDK to:

- build or load UI
- return effects from actions
- access core models
- persist module-owned data
- handle uploads and media references
- run agents, tools, and pipelines
- schedule background work
- translate user-facing strings

Do not skip around it and import from `democrai.core.*` directly from extension code.

For the package/import contract, see [Public SDK Boundary](public-boundary.md).

## Import Style

Use domain imports from the packaged SDK surface.

Examples:

```python
from democrai.sdk.decorators import action
from democrai.sdk.auth import permission_required
```

When a file needs the active request-scoped SDK object outside an injected handler argument, import the proxy explicitly:

```python
from democrai.sdk.client import active_sdk as sdk
```

Inside actions, tools, and agents, prefer the injected `module_sdk` argument instead of importing the proxy just to reach a domain.

## Domain Container Mental Model

Think of `sdk` as a namespace of runtime domains.

Common domains:

- `sdk.ui` -> build surfaces, load YAML UI, resolve resources, and compose programmatic component trees
- `sdk.effects` -> return or publish UI/runtime effects after actions complete
- `sdk.models` -> work with core-managed entities through model-driven access patterns
- `sdk.database` -> persist and query module-owned data
- `sdk.media` -> store, resolve, and retrieve uploaded or generated files through the active media provider
- `sdk.ai` -> run completions, tools, agents, and pipelines through the runtime AI layer
- `sdk.tasks` -> schedule and coordinate background work through the task runtime
- `sdk.i18n` -> resolve module-aware translations for user-facing strings
- `sdk.access` -> inspect and synchronize approval and access state exposed by the runtime
- `sdk.auth` -> apply permission checks and trusted auth helpers in module code

The root is not where you implement business logic. The root is where you choose the correct domain.

## Most Important Domain Split

This is the split that usually causes confusion:

- `democrai.sdk.models` -> core-managed entities, model-driven CRUD, model-driven schemas
- `democrai.sdk.database` -> module-owned persistence
- `democrai.sdk.media` -> persisted files and uploads, regardless of storage backend
- `democrai.sdk.effects` -> what your action returns to mutate UI/runtime behavior

If you pick the wrong domain, the code often still looks plausible but the architecture becomes wrong very quickly.

## Typical Action Shape

Most module actions follow this structure:

```python
from democrai.sdk.decorators import action
from democrai.sdk.auth import permission_required


@action("save")
@permission_required(["demo.item.create"])
async def save(ctx: dict, session: dict, module_sdk):
    values = dict(ctx.get("values") or {})
    saved = module_sdk.database.add(
        MyEntity(name=str(values.get("name") or "").strip())
    )

    return module_sdk.effects.respond(
        module_sdk.effects.notify(
            "toast",
            {"title": "Saved", "text": f"Item {saved.id} created", "variant": "success"},
        ),
        module_sdk.effects.render(),
    )
```

What matters here:

- input comes from `ctx`
- persistence goes through the correct SDK domain
- the return value is wrapped in `sdk.effects.respond(...)`

## Effects Must Be Returned Explicitly

If you define effects, show how they are returned.

Correct:

```python
return sdk.effects.respond(
    sdk.effects.navigate("/demo/anonim/index", render=True)
)
```

Also correct:

```python
return sdk.effects.respond(
    sdk.effects.ui_property_update("status_text", "text", {"literalString": "Done"})
)
```

Do not leave docs at “use effects” without showing the action return shape.

## Media Must Go Through the SDK

Uploads and file persistence must use `sdk.media`.

That is not optional documentation style. It is required because the media provider may be:

- local
- distributed
- object storage backed

If a module handles upload paths manually as if they were always local files, it will become fragile as soon as the deployment changes.

## Model Access Must Be Explicit

When the entity is a core model:

```python
listing = sdk.models.users.list(page=0, page_size=25, filters={})
```

When the entity belongs to the module:

```python
rows = sdk.database.list(MyModuleEntity, status="open")
```

The documentation must keep these two paths separate.

## SDK Pages

Use the SDK pages in the navigation for the complete domain list.
