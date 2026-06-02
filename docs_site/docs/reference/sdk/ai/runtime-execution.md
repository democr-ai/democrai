# AI: Runtime Execution

## `run_tool(name, arguments=None, context=None)`

Use this when you want deterministic execution of one registered tool.

This method is the right choice when your code already knows which tool must run and does not want to involve model reasoning.

Typical cases:

- a custom agent handler is executing returned tool calls explicitly
- a workflow step wants the logic inside a tool definition
- a module is reusing a tool as a runtime-exposed operation rather than calling unrelated internal helpers directly

What the method does:

- validates that the tool exists
- runs it through the agent runtime
- forwards the optional `context`

Example:

```python
tool_result = await sdk.ai.run_tool(
    "system.test-echo",
    arguments={
        "text": "hello",
    },
    context={"source": "example"},
)
```

Why use `run_tool(...)` instead of importing the tool function directly:

- you stay on the runtime contract
- registration remains the source of truth
- the execution gets the same runtime context shape as agent-driven tool calls

Use `context` for runtime information the tool should see but that is not part of the explicit user-facing arguments. Do not stuff business data into `context` if it should really be an input parameter of the tool.

## `run_agent(name, input="", context=None, extra_tools=None, extra_skills=None, listener=None)`

This is the main integration point for module actions that want to execute an agent.

Use it when a feature says, in plain language, "run this agent and give me the result."

This method:

- validates that the agent exists
- runs the agent through the agent runtime
- forwards an optional execution `context`
- forwards optional extra tool names and skill names for this run
- forwards an optional `listener` to observe the run

This is usually the most ergonomic method in the domain because it keeps the action code small and makes the agent runtime responsible for orchestration.

Example:

```python
result = await module_sdk.ai.run_agent(
    "system.test-agent",
    input=text,
    context={},
    extra_tools=["system.test-echo"],
    extra_skills=["system.system_test_skill"],
)

assistant_text = str(getattr(result, "content", "") or "")
```

Another example:

```python
result = await module_sdk.ai.run_agent(
    "system.test-agent",
    input=first_text,
    context={},
)

title = str(getattr(result, "content", "") or "").strip()
```

### Listener Contract

`run_agent(..., listener=callable)` lets your code observe the run while it is happening.

This is useful when the action wants to:

- stream status to the client
- record traces
- inspect tool usage
- transform runtime events into UI updates

The listener receives structured event dictionaries. Current event types include:

- `agent.run.started`
- `agent.run.finished`
- `agent.run.failed`
- `agent.completion.started`
- `agent.completion.finished`
- `agent.completion.failed`
- `agent.stream.started`
- `agent.stream.chunk`
- `agent.stream.finished`
- `agent.stream.failed`
- `agent.tool.started`
- `agent.tool.finished`
- `agent.tool.failed`

Example:

```python
async def handle_agent_event(event: dict):
    event_type = str(event.get("type") or "")
    if event_type == "agent.stream.chunk":
        text = str(event.get("text") or "")
        ...

result = await sdk.ai.run_agent(
    "reports.summary_agent",
    input="Summarize the weekly metrics",
    context={"report_id": 12},
    listener=handle_agent_event,
)
```

### What `run_agent(...)` Returns

`run_agent(...)` returns an `AgentRunResult`.

The important fields are:

- `agent_name`
- `content`
- `tool_results`
- `activated_skills`
- `raw_response`

For most module actions, `content` is the field you will read first because it is what usually reaches the UI.

## `run_pipeline(name, input="", context=None) -> dict`

Use this when your module wants to execute a registered pipeline rather than a single agent or tool.

Pipelines are the right abstraction when the feature is inherently multi-step and that orchestration has already been modeled as a runtime asset.

This method:

- validates that the pipeline exists
- executes it through the agent runtime
- forwards the optional `context`

Example:

```python
result = await sdk.ai.run_pipeline(
    "reports.generate_and_review",
    input="Generate the monthly summary",
    context={"report_id": 99},
)
```

## `cancel_request(request_id) -> bool`

Use this when the UI has a runtime request id and needs to stop the current AI
request without unloading the engine.

The method delegates to the engine runtime request registry and returns whether
the cancel signal was accepted for that request id.

Example:

```python
cancelled = module_sdk.ai.cancel_request(current_request_id)
```

Cancellation is request-scoped. It is not an engine shutdown API.

## Runtime-Managed Agents vs Custom Agent Handlers

There are still two legitimate execution styles:

### Runtime-managed agent

The runtime:

- builds or extends the conversation state
- injects declared tools
- executes tool calls
- iterates until completion or `max_iterations`

When your action simply wants the agent's result, this is the style behind `run_agent(...)`.

### Custom agent handler

The handler:

- builds the messages manually
- decides how to loop
- decides how to interpret tool calls
- may call `run_tool(...)` explicitly

But the handler does not need to give up the runtime contract.

It should resolve the provider with `get_provider_for_objective(...)`, call the provider directly, and use `run_tool(...)` for explicit tool calls.
