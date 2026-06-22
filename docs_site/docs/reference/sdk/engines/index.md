# SDK Domain: `engines`

## Overview

The `engines` domain is the SDK surface you use when your module needs to reason about AI engine providers, installation state, activation state, runtime configuration, centralized AI constants, registered instance models, and available models for a configured engine instance.

This domain is not the same thing as `sdk.ai`.

`sdk.ai` is about using AI capabilities at runtime: completions, tool calls, agent execution, pipelines, and provider-bound work. `sdk.engines` sits one layer below that. It is about the engine inventory itself: what providers exist, whether a provider is supported in the current environment, how installation is requested and tracked, how engine instances are activated or deactivated, what shared AI constants exist, which models are registered for a configured engine instance, and which models are currently available to that instance.

That distinction matters in real module code.

If you are building a chat flow, assistant, or tool pipeline, you usually start from `sdk.ai`.

If you are building setup screens, provider selection pages, activation flows, model registration screens, or configuration validation for engine instances, `sdk.engines` is usually the correct entry point.

## Two Ways Developers Use This Domain

This domain can be used in two different styles, and the documentation should keep them separate because they do not behave the same way.

### `module_sdk.engines`

Inside module actions, renders, and helpers that already receive the request-scoped SDK instance, you normally work through `module_sdk.engines`.

That object exposes the `Engines` facade. Most provider, install, runtime, and model-management methods are `async`, so you call those with `await`.

Quota-management methods are synchronous because they delegate to the core model proxies directly. The method sections below call out that distinction explicitly.

Example:

```python
available = await module_sdk.engines.list_available_models(
    engine_id="123"
)
```

### Direct Imports From `sdk.engines`

The module also exposes engine implementation contracts and helper functions
directly at import time because `democrai/sdk/engines.py` imports them at module
scope.

Provider and manifest helpers:

- `get_provider_definition(...)`
- `list_provider_definitions(...)`
- `is_engine_supported(...)`
- `provider_requirements(...)`
- `config_has_required_values(...)`

Engine/provider base classes and schemas include:

- `BaseEngine`
- `LLMProvider`
- `BaseSTTProvider`
- `BaseTTSProvider`
- `BaseCvProvider`
- `Message`
- `ContentPart`
- `CompletionOptions`
- `CompletionResponse`
- `StreamChunk`
- `Tool`
- `ToolCall`

Output parser helpers include:

- `get_output_parser(...)`
- `ParsedModelOutput`
- `StreamParseState`

Chat template helpers include:

- `get_chat_template(...)`
- `list_chat_templates(...)`

Engine call context helper:

- `current_ai_call_context`

Engine-worker media helpers:

- `democrai.sdk.engine_runtime_media.media_exists(...)`
- `democrai.sdk.engine_runtime_media.materialize_media(...)`
- `democrai.sdk.engine_runtime_media.save_model_artifact(...)`

These helpers are only for engine runtime code running inside the engine worker.
They are not available through `module_sdk.engines` or `module_sdk.media`.

These direct imports are useful in engine packages and helper code that does not
need the request-scoped SDK instance.

Example:

```python
from democrai.sdk.engines import list_provider_definitions

providers = list_provider_definitions(kind="llm")
```

That pattern is used in the current codebase for provider catalog helpers and provider support checks in the `system` module.

## Mental Model

The easiest way to understand `sdk.engines` is to split it into three responsibilities:

1. provider discovery
2. engine installation, activation, and runtime validation
3. model management and model resolution

Provider discovery answers questions such as:

- which providers exist
- what metadata is declared for a provider
- whether a provider is supported on this machine
- which provider requirements are currently missing

Installation and runtime validation answer questions such as:

- how do I trigger an engine install request
- what is the per-node install status
- can this configured engine instance be activated
- how do I activate or deactivate a configured engine instance
- is this configuration valid enough to activate the engine
- is the installed engine runtime actually importable

Model management answers questions such as:

- which shared capabilities, runtime methods, formats, sources, deployment modes, and statuses exist
- which models are already registered for this engine instance
- which models are available to this engine instance from inventory, an engine catalog, or provider API discovery
- how do I keep model activation separate from engine activation

## Identifier Semantics

The `engines` domain uses two different identifiers. Keep them separate.

| Identifier | Meaning | Example | Used By |
|---|---|---|---|
| Provider/engine slug | Static engine package id from the manifest | `openai`, `llamacpp`, `ollama` | provider discovery, source-mode metadata, schema lookup, static catalog lookup |
| Engine instance id | Database id of a configured `engine_registry` row | `123` | registered model list, available model discovery for a specific configured instance |

Methods that inspect manifests or static engine package metadata use the provider/engine slug.

Methods that inspect configured runtime state use the engine instance id because multiple rows can exist for the same provider. For example, two OpenAI-compatible instances can point at different base URLs and therefore return different available models.

Lifecycle methods use the engine instance id and own the status transition. Module code should not activate, deactivate, or mark installs by writing `status` directly through `module_sdk.models.engine_registry.update(...)`.

## Method Groups

Provider and manifest methods:

- `constants()`
- `get_provider_definition(provider_id=...)`
- `list_provider_definitions(kind=...)`
- `is_supported(engine_id=...)`
- `provider_requirements(provider_id=...)`
- `list_catalog_models(engine_id=...)`

Installation/runtime methods:

- `begin_install(engine_registry_id=..., force=..., requested_by=..., task_id=...)`
- `install_status(engine_registry_id=...)`
- `request_install(engine_id=..., force=..., requested_by=..., task_id=...)`
- `activation_requirements(engine_registry_id=...)`
- `activate_instance(engine_registry_id=...)`
- `deactivate_instance(engine_registry_id=...)`
- `sync_runtime()`
- `list_loaded_models(engine_registry_id=...)`
- `list_active_jobs()`
- `unload_loaded_model(engine_registry_id=..., model_registry_id=...)`
- `stop_engine(engine_registry_id=...)`
- `evaluate_model_resources(model_registry_id=..., context_length=..., runtime_overrides=...)`
- `check_runtime_config(engine_id=..., config=...)`
- `check_ready(engine_id=...)`

Engine runtime media helpers:

- `media_exists(storage_path)`
- `materialize_media(storage_path, destination_dir=None)`
- `save_model_artifact(storage_path, source_path)`

These are imported from `democrai.sdk.engine_runtime_media` and are valid only
inside the engine worker process.

Quota methods:

- `quota_metadata()`
- `list_quota_counters(page=..., page_size=..., filters=..., sort=...)`
- `get_quota_counter(counter_id=...)`
- `create_quota_counter(payload)`
- `update_quota_counter(counter_id=..., payload=...)`
- `delete_quota_counter(counter_id=...)`
- `list_engine_global_quota_limits(engine_registry_id=..., page=..., page_size=...)`
- `create_engine_global_quota_limit(engine_registry_id=..., payload=...)`
- `update_engine_global_quota_limit(limit_id=..., engine_registry_id=..., payload=...)`
- `list_organization_engine_quota_limits(organization_id=..., page=..., page_size=...)`
- `list_role_engine_quota_limits(role_id=..., page=..., page_size=...)`
- `list_user_engine_quota_limits(user_id=..., page=..., page_size=...)`
- `create_organization_engine_quota_limit(organization_id=..., payload=...)`
- `create_role_engine_quota_limit(role_id=..., payload=...)`
- `create_user_engine_quota_limit(user_id=..., payload=...)`
- `update_organization_engine_quota_limit(organization_id=..., limit_id=..., payload=...)`
- `update_role_engine_quota_limit(role_id=..., limit_id=..., payload=...)`
- `update_user_engine_quota_limit(user_id=..., limit_id=..., payload=...)`
- `get_engine_quota_limit(limit_id=...)`
- `delete_engine_quota_limit(limit_id=...)`

These methods are synchronous.

Legacy catalog/source-mode methods:

- `model_source_modes(engine_id=...)`
- `get_model_management(engine_id=...)`
- `get_model_schema(engine_id=..., source_mode=...)`
- `resolve_model(engine_id=..., ...)`

These methods use the provider/engine slug.

Instance model methods:

- `list_models(engine_id=...)`
- `list_available_models(engine_id=...)`

Inventory provisioning methods:

- `download_model(catalog_id=..., confirmed_resource_warning=..., task_id=...)`
- `import_model_from_source(source=..., model=...)`
- `download_model_from_source(source=..., model=..., task_id=...)`
- `delete_available_model(available_model_id=...)`

These methods use the engine instance id. The parameter name is still `engine_id` for SDK compatibility, but its value is the `engine_registry.id` when calling these methods from an engine instance page or action.

## When To Use This Domain

Use `sdk.engines` when you are building module features such as:

- an engine provider list
- a provider details page
- an installation approval flow
- an engine activation flow
- a runtime configuration screen
- a model inventory or import flow
- a UI that compares available models with models already registered for one configured engine instance

Do not use it when your problem is simply "run a completion against this model". In that case, start from `sdk.ai`.

## Subsections

The rest of this domain is split into focused pages:

- Constants and Contracts
- Provider Discovery
- Installation and Runtime
- Model Management and Resolution
- Quotas
- Engine Runtime Media

Read them in that order if you are new to the domain. That sequence matches the usual lifecycle developers encounter in real modules: discover provider, validate/support/install it, then manage the models that belong to it.
