# Agent Runtime

This package contains the internal core runtime for agents, tools, pipelines and
skills. It is not the public module contract.

Modules must use SDK APIs. This package remains core implementation.

## Concepts

- tool: small named serializable capability.
- agent: LLM-driven or handler-based orchestration unit.
- pipeline: explicit workflow composed of agents and tools.
- skill: filesystem-based context in `skill-name/SKILL.md` format.

## Flow

```text
module action
  -> democrai.sdk agent/tool/pipeline API
  -> core AgentRuntime
  -> AI orchestrator for objective/provider
  -> engine runtime when a model is needed
```

UI/actions should not call LLM providers directly for agentic behavior. They
should invoke stable SDK contracts.

## Skill Discovery

Skills are discovered from:

- packaged/runtime skills when present.
- user-specific platform directories.
- `modules/*/skills` from configured module runtime paths.
- `agents.skills.paths` from configuration.

Each skill lives in a dedicated directory:

```text
skill-name/
  SKILL.md
  assets/
```

`SKILL.md` may include YAML frontmatter. The loader returns safe metadata and
asset paths, then injects active skill content into the prompt.

## Runtime

`AgentRuntime` internally exposes:

- `run_tool(...)`
- `run_agent(...)`
- `run_pipeline(...)`

The runtime resolves providers, exposes allowed tools, activates skills and
executes the tool-call loop within configured limits.

Handler-based agents remain the right path when a provider does not support
robust tool calling or when a deterministic flow is required.

## Rules

- Tools and payloads must be serializable.
- Skills must not contain secrets.
- Pipelines must have clear inputs and outputs.
- LLM providers are resolved by runtime contracts, not hardcoded in UI.
- Modules use the SDK; core runtime remains internal.
