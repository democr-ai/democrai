# AI: Runtime Discovery

The next group of methods is about introspection rather than generation.

Use these methods when your module needs to inspect what has been registered in the runtime. Typical use cases:

- admin and diagnostics pages
- developer tooling
- dynamic UIs that let the user pick an agent or tool
- validation logic that checks registration state before execution

## `list_tools(module_name=None)`

Returns the registered tool definitions.

Use it when you want to inspect tools available in the runtime, optionally filtered to one module.

Example:

```python
tools = sdk.ai.list_tools(module_name="chat")

for tool in tools:
    print(tool.name, tool.description)
```

This is a discovery method. It does not execute anything.

## `get_tool(name)`

Returns one registered tool definition or `None`.

Use it when a module already knows the tool name and needs its registered metadata or completion-tool shape.

## `list_agents(module_name=None)`

Returns the registered agent definitions.

Use it when:

- you need to display agents in an admin UI
- you want to verify that a module registered the assets you expect
- you need metadata such as description, objective, tools, or `max_iterations`

Example:

```python
agents = sdk.ai.list_agents(module_name="chat")

for agent in agents:
    print(agent.name, agent.objective, agent.tools)
```

## `get_agent(name)`

Returns one registered agent definition or `None`.

## `list_mcp_servers()`

Returns enabled MCP server definitions.

Use it when a module needs to expose MCP choices to the user or pass active MCP
server names into an AI runtime flow.

This is a discovery method. It does not connect to the MCP server and does not
execute an MCP tool.

## `list_pipelines(module_name=None)`

Returns the registered pipeline definitions.

Use it when your module needs to inspect orchestration assets rather than individual tools or agents.

Example:

```python
pipelines = sdk.ai.list_pipelines()
```

## `get_pipeline(name)`

Returns one registered pipeline definition or `None`.

## `list_skills(allowed_names=None, module_name=None)`

Returns registered runtime skills and optionally filters them by skill name or
module name.

Use it when the module needs to know what skills are available to the runtime.

This is useful for:

- diagnostics
- curated skill pickers
- admin screens
- validation flows that expose or restrict an allowed subset

Example:

```python
skills = sdk.ai.list_skills(
    allowed_names=["system.system_test_skill"],
    module_name="system",
)

for skill in skills:
    print(skill.metadata.name, skill.metadata.summary)
```

The returned items are skill definitions with `metadata`, content, and root directory information. In most module UIs you will mainly care about the metadata.
