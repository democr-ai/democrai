# Provider Discovery

This section covers the part of `sdk.engines` that helps modules discover which providers exist and whether they are usable in the current runtime environment.

These methods are the foundation of provider lists, configuration screens, onboarding flows, and support checks.

## `provider_requirements(provider_id: str) -> dict`

This method returns the public provider requirements shape used by setup and activation UI.

Through the facade:

```python
requirements = await module_sdk.engines.provider_requirements(
    provider_id="vllm"
)
```

For synchronous helper code:

```python
from democrai.sdk.engines import provider_requirements

requirements = provider_requirements(provider_id="vllm")
```

### What It Is For

Use this method when a module needs to know whether a provider is supported, configurable, remote, or missing declared runtime dependencies.

This is the preferred module boundary for provider support and requirement logic. Module code should not reinterpret manifest dependency rules or duplicate provider support checks locally.

### Return Value

Typical payload:

```python
{
    "provider": "vllm",
    "provider_label": "vLLM",
    "supported": True,
    "support_reason": "",
    "configurable": False,
    "remote": False,
    "requires_config": False,
    "dependencies": [
        {"dependency_key": "vllm", "label": "vllm"}
    ],
    "missing_dependencies": [],
    "config_schema": [],
}
```

Use this shape for UI decisions such as:

- whether to show an install button
- whether to open a provider configuration modal
- which manifest-declared config fields to render
- which dependencies need approval before installation

## `config_has_required_values(provider_id: str, config: dict | None) -> bool`

This helper returns whether the supplied config includes the required fields declared by the provider configuration schema.

```python
from democrai.sdk.engines import config_has_required_values

ready = config_has_required_values(
    "openai",
    {"api_key": "..."},
)
```

Use this in synchronous helper code that already has a provider id and a config payload. In async module actions, `activation_requirements(engine_registry_id=...)` is usually the better entry point because it reads the stored registry config and returns a complete activation decision shape.

## `get_provider_definition(provider_id)`

This method returns the provider definition declared by engine manifests for a specific provider id.

Through the facade you call it like this:

```python
definition = await module_sdk.engines.get_provider_definition(
    provider_id="openai"
)
```

You can also import the underlying helper directly:

```python
from democrai.sdk.engines import get_provider_definition

definition = get_provider_definition("openai")
```

### What It Is For

Use this when your module already knows which provider it is working with and needs the provider metadata that was declared in the engine manifest layer.

Typical reasons:

- show provider title, description, icon, deployment mode, or capabilities
- inspect the declared model source (`inventory`, `engine_catalog`, or `provider_api`)
- inspect accepted inventory model formats and model capabilities
- inspect runtime methods exposed by the provider contract
- inspect whether the provider is configurable
- build a provider-specific configuration form from `config_schema`
- inspect declared dependencies for installation guidance

### What It Returns

The returned object is the provider section extracted from the matching engine manifest.

In practice that payload can include fields such as:

- `id`
- `title`
- `label`
- `description`
- `kind`
- `deployment`
- `model_source`
- `accepted_model_formats`
- `model_capabilities`
- `runtime_methods`
- `configurable`
- `config_schema`
- `dependencies`
- `icon_url`

The exact shape depends on the manifest, so your module should treat it as manifest-driven metadata rather than a rigid ORM-like object.

If the provider id cannot be resolved, the method returns `None`.

### Why You Would Use It

This method is useful because it keeps provider metadata centralized in engine manifests instead of forcing modules to hardcode provider knowledge.

If you write a provider page by hardcoding labels such as "OpenAI", "Ollama", or "MLX" directly in the UI layer, you immediately create drift between the manifest layer and the interface. `get_provider_definition(...)` avoids that problem by letting the UI read the authoritative metadata directly.

### Real Usage Pattern

Use `get_provider_definition(...)` when the UI needs display metadata or raw manifest fields. Use `provider_requirements(...)` when the UI needs support, config, or dependency decisions.

Example:

```python
definition = await module_sdk.engines.get_provider_definition(
    provider_id=provider
)
if not definition:
    raise ValueError(f"unknown provider: {provider}")

configurable = bool(definition.get("configurable"))
schema = list(definition.get("config_schema") or [])
```

## `list_provider_definitions(kind: str | None = None)`

This method returns the known provider definitions, optionally filtered by provider kind.

Through the facade:

```python
providers = await module_sdk.engines.list_provider_definitions(kind="llm")
```

As a direct import:

```python
from democrai.sdk.engines import list_provider_definitions

providers = list_provider_definitions(kind="llm")
```

### What It Is For

Use this when you need to build a provider catalog rather than inspect a single provider.

Typical examples:

- an engine marketplace page
- a setup wizard that lists available LLM providers
- grouping providers by deployment type or capability
- generating cards for local, hybrid, and remote providers

### How Filtering Works

The optional `kind` argument filters the provider list by the `provider.kind` declared in engine manifests.

For example, if you pass `kind="llm"`, the returned list will only include provider definitions whose manifest declares that kind.

If `kind` is omitted, all provider definitions are returned.

### Important Behavior

The manifest layer deduplicates providers by provider id. That means if multiple engine manifests refer to the same provider id, you do not get repeated provider definitions in the list.

That behavior is what makes the method suitable for provider galleries and sidebars. It returns the logical provider catalog, not raw engine rows from the database.

### Real UI Example

The current codebase uses a direct import of `list_provider_definitions()` in `modules/system/ui_helpers/engine/list.py` to build the provider catalog shown in the system engine UI.

That helper then groups providers by section using metadata like:

- deployment mode
- local section
- provider kind

This is exactly the kind of problem `list_provider_definitions(...)` is meant to solve.

Example:

```python
providers = await module_sdk.engines.list_provider_definitions()

remote_llm = [
    item
    for item in providers
    if str(item.get("deployment") or "").strip().lower() == "remote"
    and str(item.get("kind") or "").strip().lower() == "llm"
]
```

## `is_supported(engine_id: str) -> bool`

This method returns whether an engine is supported in the current runtime environment.

Through the facade:

```python
supported = await module_sdk.engines.is_supported(engine_id="ollama")
```

As a direct import:

```python
from democrai.sdk.engines import is_engine_supported

supported = is_engine_supported("ollama")
```

### What It Is For

Use this when your module needs to know whether a provider can realistically run on the current machine before offering installation or activation actions.

Examples:

- disable an install button for unsupported providers
- show a "not supported on this system" warning
- filter out providers that cannot run on the current OS, architecture, or hardware

### What It Actually Checks

This support check does not just guess based on a string comparison. It delegates to the runtime support mechanism, which evaluates the engine against the current runtime environment.

The environment includes values such as:

- operating system
- architecture
- Python version
- GPU presence and VRAM

The engine runtime then decides whether the engine is supported.

### Why This Matters

A support check is different from an installation check.

An engine can be unsupported even before you try to install it. For example:

- the engine class might not exist
- the current OS may be unsupported
- required hardware may be missing
- the runtime contract may reject the current environment

Your module should use `is_supported(...)` when the question is "should this provider even be offered here?".

Use installation flows only after the answer to that question is yes.

### Real Usage Pattern

For module UI that also needs config and dependency information, prefer `provider_requirements(provider_id=...)` so the support result travels with the rest of the provider readiness data.

## Choosing Between Facade Calls and Direct Imports

For provider discovery, the decision is usually:

- use `await module_sdk.engines.*` inside actions, renders, and async module flows
- use direct imports from `democrai.sdk.engines` in synchronous helper utilities where only provider metadata or requirement checks are needed

If you are already inside request-scoped module code, prefer the facade for consistency.
