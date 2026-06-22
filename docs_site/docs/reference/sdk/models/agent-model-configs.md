# Core Model: `agent_model_configs`

The `agent_model_configs` core model exposes persisted model configuration for
agents through the SDK core-model proxy layer.

Use `module_sdk.models.agent_model_configs` when a module needs the platform's
stored agent/model configuration rather than a module-local representation.

## Usage

```python
configs = module_sdk.models.agent_model_configs.list(
    page=0,
    page_size=50,
    filters={"agent_id": agent_id},
)
```

The core model owns the supported fields, filters, and validation behavior.
Build UI from the model schema methods when they are available.
