# Constants And Contracts

The AI engine/model vocabulary is centralized. Modules should not define their own capability names, runtime method names, model source names, deployment names, statuses, or model format strings.

Use the SDK contract instead.

## Runtime Access

Inside module code, read the contract through the `engines` facade:

```python
constants = await module_sdk.engines.constants()

model_capabilities = constants["model_capabilities"]
runtime_methods = constants["runtime_methods"]
model_sources = constants["model_sources"]
```

For Python helper code that needs symbolic constants, import from `democrai.sdk.ai_constants`:

```python
from democrai.sdk.ai_constants import AICapability, AIRuntimeMethod, AIModelSource, AIModelSourceKind

assert AICapability.CHAT == "chat"
assert AIRuntimeMethod.GENERATE_COMPLETION == "generate_completion"
assert AIModelSource.PROVIDER_API == "provider_api"
assert AIModelSourceKind.UPLOAD == "upload"
```

Use exported value tuples when building option lists:

```python
from democrai.sdk.ai_constants import AI_MODEL_CAPABILITIES, AI_MODEL_FORMATS, AI_MODEL_SOURCE_KINDS
```

## Capabilities

Capabilities describe what a model can do.

Current capability constants include:

| Constant | Value | Meaning |
|---|---|---|
| `AICapability.CHAT` | `chat` | Text/chat generation capability. |
| `AICapability.TOOL_CALLING` | `tool_calling` | Function/tool-call support for chat models. |
| `AICapability.REASONING` | `reasoning` | Reasoning-oriented model behavior. |
| `AICapability.IMAGE_TO_TEXT` | `image_to_text` | Image input interpreted into text. |
| `AICapability.EMBEDDING` | `embedding` | Text embedding support. |
| `AICapability.RERANKING` | `reranking` | Query/document reranking support. |
| `AICapability.CLASSIFICATION` | `classification` | Text classification support. |
| `AICapability.TOKEN_EXTRACTION` | `token_extraction` | Structured token extraction support. |
| `AICapability.TRIPLES_EXTRACTOR` | `triples_extractor` | Knowledge graph triples extraction support. |
| `AICapability.TTS` | `tts` | Text-to-speech support. |
| `AICapability.STT` | `stt` | Speech-to-text support. |
| `AICapability.DETECTION` | `detection` | Object detection support. |
| `AICapability.AUDIO` | `audio` | Audio domain support. |
| `AICapability.OFFLINE` | `offline` | Can run without a remote provider API. |
| `AICapability.CPU_FRIENDLY` | `cpu_friendly` | Runtime or model can run acceptably on CPU. |
| `AICapability.HIGH_THROUGHPUT` | `high_throughput` | Runtime or model is optimized for higher throughput. |

Use `normalize_capability(...)` or `normalize_capabilities(...)` when reading data that may contain legacy spellings such as `tool-calling`, `speech-synthesis`, `object-detection`, or `transcription`.

`AI_MODEL_CAPABILITIES` is the subset intended for model capability
configuration. `AI_CAPABILITIES` can include broader platform/runtime capability
labels.

### Capability-Specific Model Configuration

Capability-specific model metadata belongs in the model feature schema exposed
by `module_sdk.engines.constants()["model_feature_schemas"]`.

For embeddings, the important persisted field is `dim`, stored on the
`model_registry.extra_config` payload. Knowledge runtime configuration requires
this dimension when the selected model is used as the embedding backend.

Do not expose LLM generation fields such as `temperature`, `top_p`, or
`max_tokens` for models that do not have `chat` or `reasoning` capabilities.
Embedding, reranking, classification, STT, TTS, detection, and token extraction
models should render only their own capability/runtime option fields.

## Runtime Methods

Runtime methods describe callable provider methods. They are not capabilities.

| Constant | Value | Typical capability |
|---|---|---|
| `AIRuntimeMethod.GENERATE_COMPLETION` | `generate_completion` | `chat` |
| `AIRuntimeMethod.GENERATE_STREAM` | `generate_stream` | `chat` |
| `AIRuntimeMethod.EMBED_TEXTS` | `embed_texts` | `embedding` |
| `AIRuntimeMethod.RERANK` | `rerank` | `reranking` |
| `AIRuntimeMethod.CLASSIFY` | `classify` | `classification` |
| `AIRuntimeMethod.EXTRACT_TOKENS` | `extract_tokens` | `token_extraction` |
| `AIRuntimeMethod.EXTRACT_TRIPLES` | `extract_triples` | `triples_extractor` |
| `AIRuntimeMethod.SYNTHESIZE` | `synthesize` | `tts` |
| `AIRuntimeMethod.SYNTHESIZE_STREAM` | `synthesize_stream` | `tts` |
| `AIRuntimeMethod.TRANSCRIBE` | `transcribe` | `stt` |
| `AIRuntimeMethod.DETECT` | `detect` | `detection` |

Streaming is not a model capability. It is a runtime method or execution mode for a capability such as `chat` or `tts`.

Use `methods_for_capabilities(...)` only as a default mapping. If a provider manifest declares `runtime_methods`, prefer the declared provider contract.

## Model Sources

Model sources describe where `list_available_models(engine_id=<engine_registry.id>)` gets its rows.

| Constant | Value | Behavior |
|---|---|---|
| `AIModelSource.INVENTORY` | `inventory` | Filter `available_model_registry` by the provider's declared compatibility contract. |
| `AIModelSource.ENGINE_CATALOG` | `engine_catalog` | Read models from the engine's own catalog. |
| `AIModelSource.PROVIDER_API` | `provider_api` | Call the configured provider instance API. |

For `provider_api`, do not fall back to a static catalog. The configured instance is authoritative.

## Model Provisioning Modes

`AIModelProvisioningMode` describes how an engine catalog row is provisioned when the engine has model-management metadata.

Current constants include:

- `AIModelProvisioningMode.CATALOG` -> `catalog`
- `AIModelProvisioningMode.DEFINITION` -> `definition`
- `AIModelProvisioningMode.ARTIFACT` -> `artifact`

## Model Formats

Model formats describe persisted model artifacts or remote model identifiers.

Current constants include:

- `AIModelFormat.GGUF` -> `gguf`
- `AIModelFormat.HF_SNAPSHOT` -> `hf_snapshot`
- `AIModelFormat.PYTORCH` -> `pt`
- `AIModelFormat.ONNX` -> `onnx`
- `AIModelFormat.REMOTE` -> `remote`
- `AIModelFormat.JSON` -> `json`

Inventory compatibility is driven by provider manifest fields such as `accepted_model_formats` and `model_capabilities`.

## Registry Source Kinds

`AIModelSourceKind` describes the persisted origin of a model registry row. It is distinct from `AIModelSource`, which describes how an engine lists available models.

Current constants include:

- `AIModelSourceKind.CATALOG` -> `catalog`
- `AIModelSourceKind.HUGGINGFACE` -> `huggingface`
- `AIModelSourceKind.MANUAL` -> `manual`
- `AIModelSourceKind.PROVIDER_API` -> `provider_api`
- `AIModelSourceKind.REGISTERED` -> `registered`
- `AIModelSourceKind.UPLOAD` -> `upload`
- `AIModelSourceKind.URL` -> `url`

## Deployment And Status

Deployment constants:

- `AIDeployment.LOCAL` -> `local`
- `AIDeployment.REMOTE` -> `remote`
- `AIDeployment.HYBRID` -> `hybrid`

Registry status constants:

- `AIRegistryStatus.UNINSTALLED` -> `uninstalled`
- `AIRegistryStatus.INSTALLING` -> `installing`
- `AIRegistryStatus.INSTALLED` -> `installed`
- `AIRegistryStatus.ACTIVE` -> `active`
- `AIRegistryStatus.AVAILABLE` -> `available`
- `AIRegistryStatus.DOWNLOADED` -> `downloaded`
- `AIRegistryStatus.ERROR` -> `error`

Module UI can display these values, but lifecycle transitions must go through the engine SDK lifecycle methods:

- `module_sdk.engines.begin_install(...)`
- `module_sdk.engines.activate_instance(...)`
- `module_sdk.engines.deactivate_instance(...)`

Do not set install or activation statuses directly through `module_sdk.models.engine_registry.update(...)` from module UI actions.

## Engine Boundary

Engine implementations consume the resolved runtime configuration they receive.

They should not:

- import `core.*`
- materialize model artifacts
- inspect `available_model_registry`
- resolve media-provider paths
- invent new capabilities, statuses, formats, or method names

Model files are stored through the media provider, and the database already stores the path or reference that should be passed into the provider configuration.

When a configured model reference must become a local filesystem path for a path-only engine library, the runtime resolves it through the media SDK/provider `get_path(...)` contract before the engine implementation is invoked. Local media providers can return the existing path; distributed providers materialize the file or directory into a temporary local path.

## Related Methods

- `module_sdk.engines.constants()`
- `module_sdk.engines.provider_requirements(provider_id=...)`
- `module_sdk.engines.activation_requirements(engine_registry_id=...)`
- `module_sdk.engines.activate_instance(engine_registry_id=...)`
- `module_sdk.engines.deactivate_instance(engine_registry_id=...)`
- `module_sdk.engines.list_loaded_models(engine_registry_id=...)`
- `module_sdk.engines.unload_loaded_model(engine_registry_id=..., model_registry_id=...)`
- `module_sdk.engines.stop_engine(engine_registry_id=...)`
- `module_sdk.engines.evaluate_model_resources(model_registry_id=..., context_length=..., runtime_overrides=...)`
- `module_sdk.engines.list_available_models(engine_id=<engine_registry.id>)`
- `module_sdk.engines.list_models(engine_id=<engine_registry.id>)`
- `sdk.ai.get_provider_by_model_registry_id(model_registry_id=...)`
