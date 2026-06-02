# Model Management And Resolution

This section covers the `sdk.engines` methods used to list, provision, delete,
and resolve models for engine instances.

The current contract separates three concepts:

- model capabilities: what a model can do
- runtime methods: which provider methods can be called
- model sources: where available models come from

Do not treat these as interchangeable strings.

## Central Contract

Use `module_sdk.engines.constants()` when module code needs the framework vocabulary for capabilities, runtime methods, model formats, model sources, deployment modes, or statuses.

```python
constants = await module_sdk.engines.constants()
model_capabilities = constants["model_capabilities"]
runtime_methods = constants["runtime_methods"]
model_sources = constants["model_sources"]
```

The same constants are also available for Python code through `sdk.ai_constants`.

Capabilities describe model behavior, for example `chat`, `tool_calling`, `embedding`, `reranking`, `classification`, `token_extraction`, `tts`, `stt`, and `detection`.

Runtime methods describe callable provider methods, for example `generate_completion`, `generate_stream`, `embed_texts`, `rerank`, `classify`, `extract_tokens`, `synthesize`, `synthesize_stream`, `transcribe`, and `detect`.

Streaming is not a separate capability. It is a runtime method or mode for a capability such as `chat` or `tts`.

## Model Sources

Available models for an engine instance come from one declared source:

| Source | Meaning |
|---|---|
| `inventory` | The engine consumes models already present in the model inventory. |
| `engine_catalog` | The engine owns a catalog and may have engine-specific download or model-management behavior. |
| `provider_api` | The configured provider instance exposes models through its API. |

If an engine uses `provider_api`, `list_available_models(...)` calls that provider API for the configured instance. It must not silently fall back to a static catalog. If the provider API is unavailable, the caller should receive an error or an empty result according to the provider implementation.

Static catalog helpers remain available for catalog and inventory workflows, but they are not the model picker contract for provider API engines.

## Identifier Rules

Provider-level methods use the provider or engine slug declared by the engine manifest:

- `list_catalog_models(engine_id="llamacpp")`
- `resolve_model(engine_id="llamacpp", ...)`

Instance-level methods use the database id of a configured `engine_registry` row:

- `list_models(engine_id="123")`
- `list_available_models(engine_id="123")`

The parameter is still named `engine_id` for SDK compatibility. In instance pages and actions, pass the engine instance id, not the provider slug.

## `list_available_models(engine_id: str) -> list[dict]`

Returns the models available to one configured engine instance.

```python
available = await module_sdk.engines.list_available_models(engine_id="123")
```

Behavior depends on the provider's declared model source:

- `inventory`: filters `available_model_registry` through centralized compatibility rules.
- `engine_catalog`: returns the engine catalog as available models for that instance.
- `provider_api`: instantiates the configured provider and calls its `list_available_models()` method.

For `provider_api`, the result is instance-specific. Two OpenAI-compatible or Ollama instances can return different models.

Returned rows include:

- `id`
- `model_id`
- `label`
- `capabilities`
- `runtime_methods`
- `source_kind`
- `format`
- `summary`
- `status`

Inventory rows can also include `available_model_id`, `storage_ref`, `requirements`, `artifacts`, `interfaces`, and tags.

## `list_models(engine_id: str) -> list[dict]`

Returns model bindings already registered for one engine instance.

```python
models = await module_sdk.engines.list_models(engine_id="123")
```

Rows come from `model_registry` and include the model registry id, display label, runtime model reference, model path or provider model id, status, capabilities, runtime methods, and binding configuration.

Use this together with `list_available_models(...)` to mark available models as active or inactive in a picker.

## Model Binding Flow

A model picker for one engine instance should:

1. call `list_available_models(engine_id=<engine_registry_id>)`
2. call `list_models(engine_id=<same_engine_registry_id>)`
3. compare by `available_model_id` when present, otherwise by `model_id`
4. for `engine_catalog` rows, match downloaded inventory by the catalog row's
   provider hint and model name/reference, not by using `catalog_model_id` as the
   runtime model identity
5. activate or deactivate model bindings through module actions that persist `model_registry`
6. test or use a model through `sdk.ai.get_provider_by_model_registry_id(...)`

The engine instance can be active with zero active models. Model activation is a separate binding step.

`catalog_model_id` identifies a catalog entry. It is not the runtime identity
used by provider calls. Runtime calls use the registered model binding and the
provider/model reference stored for that binding.

## `list_catalog_models(engine_id: str) -> list[dict]`

Returns static catalog models declared by an engine package.

```python
catalog = await module_sdk.engines.list_catalog_models(engine_id="whisper")
```

Use this for inventory import, catalog download, or engine-catalog flows. Do not use it as a fallback for `provider_api` engines.

## Legacy Source-Mode Methods

The SDK still exposes these methods for legacy catalog, definition, and artifact flows:

- `model_source_modes(...)`
- `get_model_management(...)`
- `get_model_schema(...)`
- `resolve_model(...)`

They describe the older `catalog` / `definition` / `artifact` model-input contract. New engine instance model pickers should be based on `list_available_models(...)`, `list_models(...)`, and the centralized model source contract.

## Inventory Provisioning Methods

These methods manage shared rows in `available_model_registry` and their stored
artifacts. They are for model inventory flows, not for invoking a model at
runtime.

### `download_model(catalog_id: str, confirmed_resource_warning: bool = False, task_id: str | None = None) -> dict`

Resolves a catalog entry, checks resource warnings, and downloads the declared
artifact through the SDK media provider when a background `task_id` is supplied.

Typical return statuses:

- `requires_confirmation`: the catalog entry has resource warnings and the
  caller has not confirmed them
- `ready`: the entry can be downloaded, but no task id was provided
- `available`: the artifact was stored and the available-model row is ready

```python
result = await module_sdk.engines.download_model(
    catalog_id="qwen3-tts-tokenizer-12hz",
    confirmed_resource_warning=True,
    task_id=task_id,
)
```

### `import_model_from_source(source: dict, model: dict) -> dict`

Imports an already uploaded media object into shared model storage and registers
it in `available_model_registry`.

The source must use the uploaded-media shape:

```python
result = await module_sdk.engines.import_model_from_source(
    source={
        "kind": "uploaded_media",
        "storage_path": uploaded_path,
        "filename": "model.gguf",
    },
    model={
        "name": "custom-gguf",
        "label": "Custom GGUF",
        "format": "gguf",
        "capabilities": ["chat"],
        "provider_hint": "llamacpp",
    },
)
```

### `download_model_from_source(source: dict, model: dict, task_id: str | None = None) -> dict`

Downloads a URL or Hugging Face source into shared model storage and registers it
in `available_model_registry`.

Supported source kinds are `url` and `huggingface`.

```python
result = await module_sdk.engines.download_model_from_source(
    source={
        "kind": "huggingface",
        "repo": "bartowski/Llama-3.2-1B-Instruct-GGUF",
        "files": ["Llama-3.2-1B-Instruct-Q4_K_M.gguf"],
        "filename": "model.gguf",
    },
    model={
        "name": "llama-3.2-1b-q4",
        "label": "Llama 3.2 1B Q4",
        "format": "gguf",
        "capabilities": ["chat"],
        "provider_hint": "llamacpp",
    },
    task_id=task_id,
)
```

### `delete_available_model(available_model_id: int | str) -> dict`

Deletes an available-model row, deletes its stored artifact when one is present,
and removes model bindings that point at that row. Related agent and objective
references are detached or removed by the runtime cleanup flow.

```python
result = await module_sdk.engines.delete_available_model(
    available_model_id=available_model_id
)
```
