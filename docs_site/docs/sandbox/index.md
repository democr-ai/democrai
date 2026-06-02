# Sandbox

## Purpose and Mental Model

The sandbox is the runtime boundary between Democr.ai core code and extensible code.
Its purpose is to make filesystem access, network access, sensitive imports, and subprocess execution explicit instead of implicit.

That boundary matters because Democr.ai does not execute only trusted application internals. It also executes:

- modules
- module tasks
- agents, tools, and skills
- engines
- extractors
- MCP integrations

Those subjects are allowed to render UI, handle actions, call SDK services, and run business logic. They are not automatically allowed to read arbitrary paths, connect to arbitrary hosts, import sensitive native escape hatches, or start child processes.

The practical rule for developers is:

> If extensible code needs a resource outside its default runtime boundary, declare the smallest allowlist entry that covers the resource, or route the operation through the external-access approval flow.

Do not treat sandbox declarations as documentation-only metadata. The runtime reads them and uses them while enforcing access.

## What Is Enforced

The Python-level guard applies per runtime subject. It carries the active subject name, subject kind, allowed filesystem paths, allowed network targets, allowed sensitive imports, subprocess policy, and request/session identity through context variables.

At runtime it guards:

- filesystem calls made through common Python entrypoints such as `open`, `io.open`, `os`, `os.path`, `pathlib.Path`, and `shutil`
- outbound network calls made through common Python entrypoints such as `urllib`, `requests`, `httpx`, `aiohttp`, `socket`, `asyncio.open_connection`, and `http.client`
- subprocess creation through `subprocess`, `os.system`, `os.popen`, `os.fork`, and asyncio subprocess helpers
- sensitive import roots such as `ctypes`, `_ctypes`, `cffi`, and `_cffi_backend`
- context propagation into threads and thread-pool work so the guard remains active across common async/blocking bridges

On Linux, an optional OS-level network layer can also apply a process-wide egress allowlist with kernel-level rules. That layer is a second enforcement layer for network egress; the Python-level guard remains the semantic source of truth for the current subject, session, and approval state.

For Linux deployments, read [OS-Level Enforcement](os-level-enforcement.md) as part of the sandbox model. It explains Landlock filesystem restrictions, seccomp syscall blocking, iptables/cgroup network egress filtering, and the privileged helper.

## Where Developers Declare Access

For normal modules, declare long-lived module requirements in `manifest.json`:

```json
{
  "access": [
    {
      "resource_type": "network",
      "operation": "receive",
      "target": "https://api.example.com/v1/"
    },
    {
      "resource_type": "filesystem",
      "operation": "read",
      "target": "/srv/democrai/example-data"
    }
  ]
}
```

Use module-level declarations when the module itself always needs that resource during render, actions, commands, tasks, or SDK task helpers.

Declare `allowed_imports` only for sensitive native interop that the module
actually requires. It is intentionally not part of the basic example because it
is a high-trust exception, not a normal module requirement.

Some AI decorators accept asset-level access declarations for tool, agent, and pipeline definitions. Those values are registered on the AI asset definition, but module execution still runs under the module sandbox. For module code, do not rely on AI asset declarations as a replacement for module `manifest.json` sandbox declarations unless the specific runtime path you are using documents that it consumes those asset-level fields.

Engines and extractors use their own manifests. Their install/runtime sections declare structured `access` entries and `allowed_imports` for the corresponding phase. Install phases are special because the runtime may allow subprocess execution there for package installation and environment setup.

## What Happens When Access Is Missing

Missing filesystem access fails with a `PermissionError` from the process guard.

Missing network access goes through the access-policy approval service. If the active sandbox or approval state does not allow the requested operation on the target, the check can register a pending request and then raises or returns a denial depending on the call site.

The important distinction is:

- declared sandbox access is policy shipped with the module, engine, or extractor manifest and consumed by the corresponding runtime guard
- each approval decision includes the subject, resource type, operation, normalized target, and scope
- session approval is a temporary runtime decision for the current session
- permanent approval is an administrative decision stored for future checks
- denial records that a requested resource should remain disabled

Sandbox declarations should be used for expected, stable dependencies. Approval flows should be used for resources discovered at runtime or resources that need human authorization before use.

## In This Section

- [Runtime Restrictions](runtime-restrictions.md): what the runtime blocks and how the guard state works
- [Runtime Contexts](runtime-contexts.md): where sandbox or network policy is already applied
- [Allowed Targets](allowed-targets.md): how URL and host allowlists are declared and matched
- [Access Policy Contract](access-policy-contract.md): structured subject/resource/operation approval contract
- [External Access](external-access.md): how missing access becomes an approval or denial decision
- [OS-Level Enforcement](os-level-enforcement.md): Linux kernel-level filesystem, syscall, and egress controls
- [Developer Quickstart](quickstart.md): common module development scenarios
- [Troubleshooting](troubleshooting.md): how to diagnose denied filesystem, network, import, subprocess, approval, and OS-level operations
