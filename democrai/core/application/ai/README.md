# AI Application

This package owns model selection, provider orchestration, engine registry,
engine runtime processes and model inventory metadata.

External engine implementations do not live here. They are discovered from the
configured engine runtime paths and are invoked through SDK contracts and the
engine runtime boundary.

## Purpose

The AI application layer provides one internal path for model execution:

```text
module/action/core service
  -> ModelOrchestrator objective/capability/model lookup
  -> model registry and objective mapping
  -> EngineRuntimeProvider
  -> engine orchestrator / worker process
  -> engine SDK implementation
```

Callers should select a model through an objective, a capability or an explicit
model registry id, depending on the public contract they are using. They should
not select engine files, instantiate engine classes or manage worker processes
directly.

## Boundary

Core code may use this package directly.

Extensions must use the SDK:

```python
from democrai.sdk import ...
```

Modules, engines and extractors must not import from `democrai.core`.

## Key Areas

- `orchestrator.py`: resolves providers for objectives, capabilities and model
  registry ids.
- `models/`: model catalog, model registry, objective mapping and hardware
  metadata.
- `engine/manifests.py`: discovers engine manifests from
  `DEMOCRAI_ENGINES_PATH`.
- `engine/runtime/`: engine runtime manager, provider facade, worker process
  lifecycle, access policy and media materialization.
- `engine/orchestrator/`: background gRPC orchestration for engine workers.
- `engine/worker.py`: worker-process entrypoint that loads and invokes engine
  implementations.
- `engine/batching.py`: method-level batching when an engine declares that a
  runtime method can batch requests.
- `config_access.py` and `config_crypto.py`: runtime engine configuration
  access and secret handling.

## Runtime Methods

Runtime methods are declared by engine manifests and implemented by engine
providers. Common methods include:

- `generate_completion`
- `generate_stream`
- `embed`
- `extract_entities`
- `transcribe`
- `synthesize`
- `detect`

The engine manifest is the source of truth for which methods are available and
how they may be batched. The UI must not infer runtime support from local
hardcoded lists.

## Model Options

Model options come from model configuration and public SDK helpers. Callers must
only send options that are compatible with the selected model and provider.

Reusable option logic belongs in the AI SDK surface, not in individual modules
or UI pages.

## Tool Calling, MCP, Agents and Skills

Tool calling and agent execution share the same provider/runtime path. The model
pipeline may expose:

- local tools registered through the runtime.
- MCP tools resolved by the MCP runtime.
- agents and skills selected by the caller through public contracts.

Tool schemas and tool results must be serializable. Tool execution errors should
be reported as structured runtime output whenever possible instead of crashing
the caller.

## Media and Attachments

The main process owns application storage and access checks. Engine workers
receive materialized inputs that are already readable inside the worker access
context.

Workers must not open module storage or use application SDK media APIs to fetch
attachments.

## Observability

Every model execution should be traceable through pipeline/request metadata.
Runtime events, usage events and pipeline steps belong in the common provider
path so completion, streaming, tool calling and media handling are observable in
the same way.

## Rules

- Do not instantiate engine implementations outside the engine runtime.
- Do not bypass the orchestrator/provider path from modules or UI actions.
- Do not put model selection logic in UI code.
- Do not use `catalog_model_id` as runtime identity.
- Keep engine process context separate from the main application context.
- Keep provider options and capability resolution centralized in the SDK/core
  contracts.
