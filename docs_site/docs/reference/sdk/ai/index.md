# SDK Domain: `ai`

## Purpose

`sdk.ai` exposes two things:

- provider resolution for AI objectives and explicit model bindings
- registered agent, tool, pipeline, and skill runtime access

It does not wrap provider methods. After resolving a provider, call the provider directly:

```python
result = await sdk.ai.get_provider_for_objective("chat")
if result.get("status") != "ok":
    raise RuntimeError(result.get("error", "Provider unavailable"))

provider = result["provider"]
response = await provider.generate_completion(
    messages=[{"role": "user", "content": "Reply briefly."}],
    options={"temperature": 0.2},
)
```

Provider methods are owned by the provider contract, not by `sdk.ai`.

Provider resolution is lazy. `get_provider_for_objective(...)` and
`get_provider_by_model_registry_id(...)` return a provider handle but do not
preload the model into memory. Call `warmup_provider(provider, wait=True|False)`
when a flow wants explicit model warmup before the first real provider method.

## Choosing The Right Entry Point

Use `get_provider_for_objective(...)` when objective routing should choose the current provider for work such as chat, embedding, rerank, classification, token extraction, detection, transcription, or synthesis.

Use `get_provider_by_model_registry_id(...)` when the user selected one exact model row and objective routing would be wrong.

Use `warmup_provider(...)` after provider resolution when model loading should
be explicit, measurable, or started in the background before the first AI call.

Use `get_composer_options_for_capability(...)` when a page needs the composer
configuration for the active model assigned to a capability, such as `chat`.

Use `get_composer_options_by_model_registry_id(...)` when a page already has a
specific `model_registry` row.

Use `cancel_request(...)` when a UI or action has a runtime request id and needs to ask the engine runtime to stop that request.

Use `run_agent(...)` when a module wants the agent runtime to manage the loop and tool execution.

Use `run_tool(...)` when the code already knows which registered tool must run.

Use `list_*` and `get_*` discovery methods when a module needs registered agent, tool, pipeline, skill, or MCP definitions.

## In This Section

- [Provider Resolution](provider-resolution.md)
- [Composer Options](composer-options.md)
- [Runtime Discovery](runtime-discovery.md)
- [Runtime Execution](runtime-execution.md)
- [Core Agent Tools](core-agent-tools.md)
