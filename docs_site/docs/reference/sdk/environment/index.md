# SDK Domain: `environment`

The `environment` domain is the SDK surface for managed runtime environment variables.

Modules, engines, and extractors must not mutate `os.environ` directly. They declare configurable variables in their manifest, and management screens call `sdk.environment`.

## Manifest Contract

Declare variables with the top-level `environment` key:

```json
{
  "environment": [
    {
      "name": "HF_TOKEN",
      "label": "Hugging Face token",
      "description": "Token used for gated Hugging Face assets.",
      "secret": true,
      "required": false
    }
  ]
}
```

The runtime accepts declarations from module, engine, and extractor manifests. Definitions are kept in the core runtime registry. Persisted values are stored separately and encrypted in the database. Only declared variables are manageable through the SDK; ad-hoc names are rejected.

Reserved names such as `DEMOCRAI_*`, `PATH`, `PYTHONPATH`, `LD_PRELOAD`, and `LD_LIBRARY_PATH` are not configurable through this domain.

## Methods

```python
definitions = await module_sdk.environment.list_definitions()
rows = await module_sdk.environment.list_variables()
```

`list_variables(...)` returns manifest definitions merged with configured DB values. It never returns decrypted secret values. Rows expose `has_value`, `masked_value`, `enabled`, and `configured`.

```python
await module_sdk.environment.set_value(
    subject_kind="engine",
    subject="qwen_tts",
    name="HF_TOKEN",
    value="hf_...",
    enabled=True,
)
```

```python
await module_sdk.environment.delete_value(variable_id=12)
await module_sdk.environment.apply(name="HF_TOKEN")
```

## Multinode Behavior

Create, update, and delete operations are applied locally and then broadcast to the runtime stream `system.environment.events`.

The event payload contains only metadata:

- `event_id`
- `operation`
- `subject_kind`
- `subject`
- `name`
- `source_node_id`

The secret value is never sent over the stream. Each node receives the event, reloads the value from the database, decrypts locally, and applies it to its own process environment.

The core applies managed variables on bootstrap after migrations are available. Updates after bootstrap are propagated by the stream consumer.

If more than one subject configures the same environment variable name, the process environment can only hold one value. The latest enabled configured row for that name wins; deleting or disabling it causes the core to reapply the next enabled row, if one exists.

