# Core Concepts

This page defines the concepts that keep showing up across the module documentation.

## Runtime Areas

- `democrai/core/`: backend runtime, orchestration, storage, protocols, and internal services
- `democrai/sdk/`: public Python boundary for modules, engines, and extractors
- `clients/qtdesktop/`: Qt desktop client
- `clients/webclient/`: browser client
- `modules/`: extension modules loaded through the SDK boundary
- `engines/`: installable AI engines loaded through the SDK boundary
- `extractors/`: installable extractors loaded through the SDK boundary

The important consequence is: module code is not allowed to treat the desktop transport, web transport, storage backend, or runtime wiring as implementation details it can bypass.

## Runtime Modes

The executable supports two public runtime modes:

- `desktop`
- `server`

Behavior:

- `python main.py` defaults to `desktop`
- `desktop` mode uses **IPC** as the primary backend transport
- `desktop` mode starts `clients/qtdesktop` by default
- `server` mode exposes **WebSocket/HTTP** and starts no client by default
- `desktop --http` keeps IPC and also enables HTTP/WebSocket
- `--client webclient` asks the runner to execute `yarn dev` in the web client root

The transport is not a module concern. Modules must expose actions, pages, tools, agents, and effects in a transport-agnostic way.

The runner also sets the runtime extension path environment variables when they are missing:

- `DEMOCRAI_MODULES_PATH`
- `DEMOCRAI_ENGINES_PATH`
- `DEMOCRAI_EXTRACTORS_PATH`

## Setup Mode

If `config.yaml` is missing, bootstrap enters **setup mode**.

In setup mode:

- minimal local providers are initialized
- full migrations and normal provider wiring are deferred
- the installation flow is expected to produce the real config

This matters when you write setup-sensitive code or document the first boot experience.

## Module

A module is an extension package discovered from the runtime module paths.

Typical responsibilities:

- UI pages under `ui/*`
- action entrypoints under `actions/*`
- helper logic under `utils/actions/*` and `utils/ui/*`
- tools, agents, hooks, commands, and other registered assets

## Render

A render entrypoint is a route/page function that returns a `democrai.sdk.ui.Builder`.

Typical render responsibilities:

- load YAML or create the component tree
- seed the initial UI state
- set component properties or bindings
- keep business logic light

Render should not turn into a giant action handler.

## YAML-first UI

The documentation should privilege **YAML-first UI authoring** because it is easier to read, easier to translate, and easier to keep stable.

That does not mean Python-defined UI is unsupported.

Python-first UI still exists and is used in real modules such as `demo`, but the preferred documentation path is:

1. define static structure in YAML
2. load it from `democrai.sdk.ui.load(...)` or the injected SDK object
3. use actions and effects for runtime mutations

## Action

An action is a registered entrypoint decorated with `@action(...)`.

UI calls actions by fully qualified name:

```text
module_name.action_name
```

Action handlers usually:

- read `ctx`
- call the relevant SDK domains
- return effects through `sdk.effects.respond(...)`

## Effects

Effects are typed runtime instructions returned by actions.

Common examples:

- `sdk.effects.render()`
- `sdk.effects.navigate(...)`
- `sdk.effects.notify(...)`
- `sdk.effects.ui_property_update(...)`
- `sdk.effects.ui_collection_append/remove/replace(...)`

Important: effects are not usually returned raw one by one. They are wrapped in `sdk.effects.respond(...)`.

Example:

```python
return sdk.effects.respond(
    sdk.effects.notify(
        "toast",
        {"title": "Saved", "text": "Changes applied", "variant": "success"},
    ),
    sdk.effects.navigate("/demo/anonim/index", render=True),
)
```

## Store and Binding

The UI can bind properties to client-side store state.

Main scopes:

- page store: route-local state
- global store: cross-page/shared client state

Use bindings, `show_if`, `hide_if`, and capability-based updates to avoid unnecessary full rerenders.

## Surface

A surface is a UI target area.

Examples:

- the main content surface
- auxiliary surfaces such as drawers or modals

Some effects and UI messages target a specific surface rather than replacing the entire page tree.

## Tool / Agent / Pipeline

### Tool

A tool is a callable runtime capability registered with `@tool(...)`.

Use it when you want a structured operation exposed to the agent runtime.

### Agent

An agent is a runtime AI asset registered with `@agent(...)`.

If the agent declares `tools=[...]`, those tools belong to the agent contract.

Today that means:

- in the runtime-managed agent loop, the runtime injects and uses them directly
- in a custom handler, resolve the provider with `sdk.ai.get_provider_for_objective(...)` and pass the registered tools explicitly when calling the provider

For normal module integration, call the agent with `sdk.ai.run_agent(...)`.

If the action needs live visibility into what the agent is doing, pass `listener=` to `sdk.ai.run_agent(...)`.

### Pipeline

A pipeline is a deterministic orchestration asset, useful when you want an explicit runtime flow instead of open-ended agent behavior.

## Core Models vs Module Models

This distinction must stay explicit in every guide:

- `sdk.models.<entity>` is for **core-managed entities**
- `sdk.database` is for **module-owned tables**

Examples:

- `sdk.models.users` -> core users table and model-driven schemas
- `sdk.database.add(MyModuleEntity(...))` -> module-specific persistence

Do not mix them.

## Media

Dynamic files are not “just local files”.

The active media provider may be:

- local filesystem
- distributed/object-backed storage

That is why modules must use `sdk.media` for uploads, downloads, persistence, file references, and retrieval.

If a module bypasses `sdk.media`, it may work locally and then break as soon as the deployment switches media backend.

## Model Access Scope

When using `sdk.models`, access scoping is handled by the model layer.

The module author does not manually inject ownership constraints like `user_id` or `organization_id` into every CRUD call unless the specific API explicitly requires it for another reason.

The model layer is responsible for:

- access-level prefilters
- allowed filters enforcement
- organization/user visibility constraints

This is one of the reasons modules should prefer `sdk.models` instead of custom direct data access for core entities.
