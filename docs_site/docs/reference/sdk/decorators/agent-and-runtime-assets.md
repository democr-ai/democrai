# Decorators: Agent and Runtime Assets

## Agent and Runtime Decorators

These decorators register runtime assets for the agent runtime.

Runtime asset names are dot-qualified names made of atomic segments. Each segment
must match `^[A-Za-z0-9-]+$`: ASCII letters, digits, and hyphens only. The dot is
reserved as the namespace separator. Do not use underscores in registered tool,
agent, MCP server, or module names.

## `tool(...)`

Use this to register a callable tool definition for the agent runtime.

### What it does

The decorator registers:

- the resolved tool name
- the Python function
- the description
- the JSON input schema
- confirmation requirements
- access rules used by the sandbox
- the owning module name

If you omit `description`, the decorator falls back to the function docstring when available.

If you omit `input_schema`, it defaults to an empty object schema.

### Why use it

Use `@tool(...)` when the callable is meant to be invoked through the agent runtime or exposed to an agent as a tool contract.

This is not just "any helper function". It is a runtime tool definition.

### Example

```python
from democrai.sdk.decorators import tool

@tool(
    name="demo.echo",
    description="Echoes text for a runtime tool test.",
    input_schema={
        "type": "object",
        "properties": {"text": {"type": "string"}},
    },
)
async def echo(text: str = ""):
    return {"text": text}
```

That is the correct pattern:

- stable module-qualified tool name
- explicit description
- explicit input schema

Do not use legacy `allowed_urls` or `allowed_paths` arguments. Runtime assets use
the documented access contract.

## `agent(...)`

Use this to register an agent definition backed by a Python handler.

### What it does

The decorator creates and registers an `AgentDefinition` containing:

- name
- description
- objective
- system prompt
- declared tools
- declared skills
- max iterations
- access rules used by the sandbox
- MCP server list
- the Python handler

It also normalizes and validates the `mcp_servers` list. Notably, the wildcard `*` is rejected.

### Why use it

Use `@agent(...)` when the module is defining a real agent asset that should be discoverable and executable by the runtime.

This is the decorator that connects your Python handler to the runtime agent registry.

### Example

```python
@agent(
    "demo-agent",
    description="Demo agent.",
    objective="chat",
    tools=[
        "demo.echo",
    ],
    max_iterations=5,
)
async def demo_agent(input: str = "", context: dict | None = None):
    ...
```

This is a good example because it shows the normal pattern:

- declare the agent contract
- declare the tool surface explicitly
- keep the handler responsible for the actual orchestration

## `pipeline(...)`

Use this to register a pipeline definition composed of tool, agent, or parallel steps.

### What it does

The decorator normalizes each step into `PipelineStepDefinition`, including nested steps for parallel branches, and registers a `PipelineDefinition`.

It accepts either:

- already-built `PipelineStepDefinition` objects
- dict-based step declarations

That makes it useful for both strongly typed and declarative pipeline definitions.

### Why use it

Use `@pipeline(...)` when the runtime asset you want to expose is not a single agent or tool, but a multi-step orchestration contract.
