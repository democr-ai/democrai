# Sandbox Runtime Contexts

## Runtime Contexts That Already Impose Sandbox or Policy

Developers normally do not instantiate the guard directly. The runtime enters the correct sandbox context around the main extensibility surfaces.

If code runs through one of the contexts below, its filesystem, network, import, and subprocess behavior is already constrained by the runtime. The developer's job is to declare the required resources in the right manifest or use the approval flow, not to create a custom guard.

### Module Runtime

Module render, action, and command invocation runs under a process guard with:

- base runtime paths
- the application data directory
- the module directory
- module structured `access` filesystem entries
- module structured `access` network entries
- module `allowed_imports`
- request user, organization, and session identity when available

Put stable module filesystem and network dependencies in the module `manifest.json`.

### Module Tasks

Module tasks also run under a process guard. The task runtime resolves the module name and applies the module's path and network declarations.

This means a background task should not need different network or filesystem access declarations from the foreground module unless the module manifest is incomplete.

Tasks started from an interactive request preserve the originating user, organization, and session. Tasks started by long-running or scheduled runtime code may have user identity without a session. In that case, external-access requests can still be approved permanently or denied, but session approval is not valid.

### SDK Task Helpers

The SDK task helpers rebuild the request context and enter a module sandbox for blocking work.

`run_blocking(...)` keeps the module guard active while the blocking callable runs in a worker thread.

`run_subprocess(...)` is the supported way for module code to start a child process. It enters a guarded task context with `allow_subprocess=True` and injects sandbox environment variables into the child process:

- `DEMOCRAI_NETWORK_SUBJECT`
- `DEMOCRAI_NETWORK_SUBJECT_KIND`
- `DEMOCRAI_ACCESS`

The child process can use the environment-based guard helpers to inherit the intended network and path policy.

When `sandbox.os.enabled` is true, SDK subprocess execution is routed through the sandbox launcher. The launcher reads the active parent guard policy, applies the available OS-level filesystem rules to the child process, and then executes the requested command. On Linux with Landlock support, filesystem access in the child is restricted from the same access rules carried by the parent guard. On platforms where OS-level filesystem enforcement is unavailable, the subprocess still runs through the SDK path, but the OS layer does not add filesystem isolation.

The runtime also injects request identity variables when they exist:

- `DEMOCRAI_USER_ID`
- `DEMOCRAI_ORGANIZATION_ID`
- `DEMOCRAI_SESSION_KEY`

These variables are for runtime propagation only. Guarded code cannot mutate `DEMOCRAI_*` values while the process guard is active.

### Engine Runtime

Engine execution is sandboxed with:

- engine runtime paths
- engine manifest runtime `access` filesystem entries
- engine manifest runtime `access` network entries
- engine manifest runtime `allowed_imports`
- configured URLs from manifest-declared `allowed_config_urls`

Engine install phases use the install section instead, add installer-oriented default package hosts, and enable subprocess execution for installation work.

Declare engine runtime dependencies under the manifest `runtime` section. Declare install-only downloads under `install`.

### Extractor Runtime

Extractors follow the same pattern as engines:

- extractor runtime `access` filesystem entries
- extractor runtime `access` network entries
- extractor runtime `allowed_imports`

Extractor install phases use install declarations and enable subprocess execution only for that phase.

Declare extractor dependencies in the matching manifest phase.

### MCP Runtime

The MCP runtime also uses a process guard. In that context it sets:

- `allowed_paths=[]`
- `allowed_targets` derived from the MCP server endpoint
- `allow_subprocess=False`
- `include_runtime_paths=False`

Before fetching MCP tools, the runtime also checks external access for the configured MCP endpoint. That means the endpoint must be approved or allowed before the runtime contacts it.

MCP servers are intentionally narrow: the guard allows the configured endpoint, not arbitrary network access.

### AI Tool, Agent, and Pipeline Runtime

Registered AI tools, agents, and pipelines enter their own sandbox subjects when executed through the agent runtime:

- tool execution uses `subject_kind="tool"`
- agent execution uses `subject_kind="agent"`
- pipeline execution uses `subject_kind="pipeline"`

These subjects append to the current `subject_chain`. For example, an interactive module action that runs a pipeline, which runs an agent, which calls a tool, produces a chain like:

```text
module -> pipeline -> agent -> tool
```

The runtime consumes access declarations on the corresponding tool, agent, or pipeline definition. Those declarations narrow the nested subject; they do not replace the outer module manifest for ordinary module execution.

### Media and External URL Runtime Flows

When the runtime fetches, streams, or proxies external media URLs, it does so inside an active network policy context with the allowed targets derived for that URL flow.

These flows are not a general-purpose bypass for modules. They are runtime services that build a scoped policy for the URL operation they perform.

## When to Add an Allow Declaration

Add an allow declaration when all of these are true:

- the resource is required for normal operation
- the target is stable enough to review before deployment
- the scope can be made specific
- the code will run through one of the guarded runtime contexts

Use the external-access approval flow instead when:

- the target is user supplied
- the target is discovered dynamically
- an administrator must decide at runtime
- the resource should be available only for one session

If neither applies, the operation should remain blocked.
