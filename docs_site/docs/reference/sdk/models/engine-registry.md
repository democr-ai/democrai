# Core Model: `engine_registry`

The `engine_registry` core model is the central registry for configured engine instances.

If your module needs to create, inspect, update, or remove engine registrations, this is the model that owns that data.

It is more than a plain table wrapper because it also handles provider config encryption and runtime side effects related to sandbox/network allowlist refresh.

## What This Model Represents

Rows include:

- `id`
- `name`
- `provider`
- `config`
- `status`
- `supported`

The important field here is `config`: the model decrypts it on output and encrypts it on write according to the engine provider rules.

## Typical Use Cases

Use `module_sdk.models.engine_registry` when you need to:

- list configured engines
- create a new engine entry
- update engine configuration
- remove an engine registration
- build provider-specific admin pages

Use `module_sdk.engines` for lifecycle operations such as install, activation, and deactivation. Those flows own status transitions and runtime synchronization.

## Listing Engines

Example:

```python
listing = module_sdk.models.engine_registry.list(
    page=0,
    page_size=200,
    filters={"provider": "ollama"},
)
```

Supported filters include:

- `id`
- `name`
- `provider`
- `status`
- `supported`

## Viewing One Engine

Example:

```python
engine = module_sdk.models.engine_registry.view(engine_id)
```

Use this when rendering engine detail pages or when a later action needs the current decrypted config.

## Creating An Engine

Example:

```python
created = module_sdk.models.engine_registry.create(
    {
        "name": "Local Ollama",
        "provider": "ollama",
        "config": {"base_url": "http://localhost:11434"},
        "status": "uninstalled",
        "supported": True,
    }
)
```

### What It Validates And Does

The model:

- requires `name` and `provider`
- rejects duplicate engine names
- requires `config` to be an object when provided
- encrypts provider-sensitive config fields before persistence
- emits an engine allowlist refresh event after creation

That last side effect matters operationally. This is one reason direct database writes are the wrong abstraction for this data.

## Updating An Engine

Example:

```python
updated = module_sdk.models.engine_registry.update(
    engine_id,
    {
        "config": {"base_url": "http://127.0.0.1:11434"},
    },
)
```

### Important Behavior

The update path is careful with encrypted config fields:

- if you change provider, config may need to be re-encrypted for the new provider
- if encrypted fields are omitted, the model preserves the existing plaintext values
- if encrypted-looking values are passed back in, the model resolves them correctly before re-encrypting

This is exactly the kind of logic you want to centralize in the core model layer.

Do not update lifecycle fields such as `status` from module UI code. Use:

- `module_sdk.engines.begin_install(...)`
- `module_sdk.engines.activate_instance(...)`
- `module_sdk.engines.deactivate_instance(...)`

## Deleting Engines

Example:

```python
deleted = module_sdk.models.engine_registry.delete(engine_id)
```

Use this for admin-level cleanup of registry entries, not for runtime lifecycle operations that should be expressed through higher-level engine flows.

## Table And Filter Schemas

The model exposes `table_model()` and `filters_model()` and they are useful for engine admin pages.
