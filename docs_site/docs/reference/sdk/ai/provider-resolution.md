# AI: Provider Resolution

## `get_provider_for_objective(objective, required_capabilities=None, prefer_local=None) -> dict`

Resolve the provider selected by the model orchestrator for one objective.

The SDK does not wrap the provider. It forwards the request to the core
orchestrator and returns the result.

Provider resolution is intentionally lazy: it validates and returns a provider
handle, but it does not preload the model into memory. The first provider method
call can still load the runtime if the model is not already active. Use
`warmup_provider(...)` when you want to preload explicitly.

The returned dictionary uses this shape:

- `status`
- `provider` when resolution succeeds
- `error` when resolution fails

Example:

```python
result = await sdk.ai.get_provider_for_objective(
    "chat",
    required_capabilities=["chat"],
)

if result.get("status") != "ok":
    raise RuntimeError(result.get("error", "Provider unavailable"))

provider = result["provider"]
response = await provider.generate_completion(
    messages=[
        {"role": "system", "content": "Answer briefly."},
        {"role": "user", "content": "Summarize the ticket."},
    ],
    options={"temperature": 0.2},
)
```

Use `required_capabilities` only when the feature truly depends on that capability. Use `prefer_local` as a routing hint, not as a guarantee.

Provider methods are called directly:

```python
embeddings = await provider.embed_texts(texts=["First text", "Second text"])
ranked = await provider.rerank(query="capital of France", texts=["Paris", "Berlin"])
labels = await provider.classify(texts=["I like this result."])
tokens = await provider.extract_tokens(text="Alice works at Example Corp.")
```

## `warmup_provider(provider, wait=True) -> dict`

Explicitly warm up a provider returned by `get_provider_for_objective(...)` or
`get_provider_by_model_registry_id(...)`.

Warmup asks the engine orchestrator to resolve and load the provider runtime
without invoking an AI method such as completion, embedding, transcription, or
reranking.

Use it when you want model loading to be explicit instead of hidden in the first
real call.

```python
result = await sdk.ai.get_provider_for_objective("embedding")
if result.get("status") != "ok":
    raise RuntimeError(result.get("error", "Provider unavailable"))

provider = result["provider"]
warmup = await sdk.ai.warmup_provider(provider, wait=False)
request_id = warmup["request_id"]
```

With `wait=False`, the call returns immediately after scheduling the warmup:

```python
{
    "status": "queued",
    "request_id": "...",
    "selector_type": "objective",
    "objective": "embedding",
}
```

With `wait=True`, the call waits until the runtime is ready and includes the
measured warmup duration:

```python
warmup = await sdk.ai.warmup_provider(provider, wait=True)
print(warmup["warmup_ms"])
```

Use `wait=True` for model test pages, calibration flows, and diagnostics where
the user expects to see warmup time separately from invocation time. Use
`wait=False` for chat, upload, or background flows where the UI should remain
responsive while the runtime prepares.

If a real provider method is called while a warmup for the same engine row and
runtime config is still in progress, the runtime converges on the same engine
handle instead of creating a duplicate model instance.

## Opt-in Knowledge Ingestion For Completion Calls

`generate_completion(...)` and `generate_stream(...)` can persist the call as
knowledge when the caller opts in with `ingest=True`.

The default is `False`. Runtime AI calls are private unless the module
explicitly asks for knowledge ingestion.

Use `ingest_meta` for application metadata that later needs to be used as a
retrieval filter, such as module name, chat id, thread id, workspace id, or a
feature-specific scope. Keep those values in metadata; do not pass them as
separate persistence identifiers.

Example:

```python
response = await provider.generate_completion(
    messages=[
        {"role": "user", "content": "Summarize this discussion."},
    ],
    options={"temperature": 0.2},
    ingest=True,
    ingest_meta={
        "module_name": "chat",
        "chat_id": "chat_42",
        "thread_id": "thread_7",
    },
)
```

For streaming calls, ingestion happens after the stream completes successfully:

```python
async for chunk in provider.generate_stream(
    messages=[
        {"role": "user", "content": "Continue the conversation."},
    ],
    options={"temperature": 0.2},
    ingest=True,
    ingest_meta={
        "module_name": "chat",
        "chat_id": "chat_42",
    },
):
    ...
```

The caller does not pass `user_id`, `organization_id`, or `pipeline_id`.

- `user_id` and `organization_id` are resolved from the active request context.
- `pipeline_id` is assigned by the AI pipeline runtime and becomes the knowledge
  source id.
- chat or module identifiers belong in `ingest_meta` so retrieval can filter on
  them without binding module entities to core database columns.

Only textual user/assistant/tool/task messages and the final assistant output
are ingested. System messages are not persisted into knowledge.

## `get_provider_by_model_registry_id(model_registry_id, confirm_swap=False) -> dict`

Resolve a provider for one explicit `model_registry` row.

Use this for model test pages, calibration flows, benchmark actions, and admin diagnostics where the user has already selected one model binding.

This method does not let objective routing choose another model.

The return value is a dictionary with:

- `status`
- `provider` when resolution succeeds
- `model` when resolution succeeds
- `error` when resolution fails
- `to_unload` when resource confirmation is required

Possible `status` values:

- `ok`: `provider` was resolved and is ready to receive calls.
- `error`: resolution failed; inspect `error`.
- `need_confirmation`: loading the model requires unloading other runtime instances.

Example:

```python
result = await sdk.ai.get_provider_by_model_registry_id(42)

if result.get("status") != "ok":
    raise RuntimeError(result.get("error", "Model provider unavailable"))

provider = result["provider"]
await sdk.ai.warmup_provider(provider, wait=True)
response = await provider.generate_completion(
    messages=[{"role": "user", "content": "Reply with one short sentence."}],
    options={"max_tokens": 32},
)
```

The model path/reference is resolved by the inventory/media-provider flow before the provider is built. Engine implementations receive the resolved config and should not reach into core registries.
