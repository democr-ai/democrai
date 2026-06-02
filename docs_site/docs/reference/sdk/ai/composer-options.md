# AI: Composer Options

Composer options are resolved by `sdk.ai`, not by individual modules.

Use these methods when a page needs to configure a `Composer` for an LLM model
without loading the model into memory.

## `get_composer_options_for_capability(capability) -> dict`

Resolve composer configuration from the first active model assigned to a
capability through `model_capability_priority`.

```python
composer = sdk.ai.get_composer_options_for_capability("chat")
```

## `get_composer_options_by_model_registry_id(model_registry_id) -> dict`

Resolve composer configuration for one explicit `model_registry` row.

```python
composer = sdk.ai.get_composer_options_by_model_registry_id(12)
```

## Return Shape

Both methods return the same shape:

```python
{
    "configured": True,
    "status": "active",
    "model_registry_id": 12,
    "model_capabilities": ["chat", "tool_calling", "image_to_text"],
    "options_schema": {"fields": []},
    "options": {},
    "options_editable": False,
}
```

When the model supports a composer-editable option, such as reasoning activation,
the SDK adds the field to `options_schema` and its default value to `options`.

```python
{
    "options_schema": {
        "fields": [
            {
                "name": "extra.reasoning",
                "label": "Reasoning",
                "type": "checkbox",
                "value": False,
            }
        ]
    },
    "options": {
        "extra.reasoning": False,
    },
    "options_editable": True,
}
```

Modules should pass these values to the composer instead of parsing model
capabilities or `extra_config` directly.

```python
composer = sdk.ai.get_composer_options_for_capability("chat")

builder.set_store(
    "/my_module/composer",
    {
        "disabled": not composer["configured"],
        "model_capabilities": composer["model_capabilities"],
        "options": composer["options"],
        "options_schema": composer["options_schema"],
        "options_editable": composer["options_editable"],
    },
    scope="page",
)
```

These methods only read model configuration. They do not instantiate providers,
warm up engines, or load local models into memory.
