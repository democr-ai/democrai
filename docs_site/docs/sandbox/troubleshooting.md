# Sandbox Troubleshooting

Use this page when a module, task, engine, extractor, or MCP integration is blocked by the sandbox.

Start from the exact error. The error usually tells you which layer denied the operation.

## Filesystem Denied

Error shape:

```text
sandbox_filesystem_denied:<subject>:<path>
```

This means the concrete path is outside the active filesystem roots.

Check:

1. Identify the subject in the error.
2. Identify the subject kind from the runtime path: module, module task, engine, extractor, or MCP.
3. Check the matching declaration location.
4. Resolve symlinks and relative paths mentally as absolute paths.
5. Confirm the requested path is exactly the declared root or below it.

For modules and module tasks, the declaration belongs in module `manifest.json`:

```json
{
  "access": [
    {
      "resource_type": "filesystem",
      "operation": "read",
      "target": "/srv/democrai/reports"
    }
  ]
}
```

For engines and extractors, use the phase that actually runs the code:

```json
{
  "runtime": {
    "access": [
      {
        "resource_type": "filesystem",
        "operation": "read",
        "target": "/srv/democrai/models"
      }
    ]
  }
}
```

If the path is user-selected or administrator-selected at runtime, use the external-access flow instead of adding a broad manifest root.

## Filesystem FD Denied

Error shape:

```text
sandbox_filesystem_fd_denied:<subject>:<key>
```

This means normal runtime code attempted a file-descriptor based path operation through fields such as `dir_fd`, `src_dir_fd`, or `dst_dir_fd`.

Those operations are relaxed only in subprocess/install contexts where package installers and cleanup code need them. Normal module runtime should use ordinary path operations under declared filesystem `access` entries.

## Sensitive Import Denied

Error shape:

```text
sandbox_module_denied:<root>
```

This means the subject imported a sensitive native escape hatch without declaring it. Current sensitive roots are:

- `ctypes`
- `_ctypes`
- `cffi`
- `_cffi_backend`

Declare the root only when native interop is truly required:

```json
{
  "allowed_imports": ["ctypes"]
}
```

If the import is incidental through a dependency, prefer changing the dependency path before allowing native interop broadly.

## Subprocess Denied

Error shape:

```text
sandbox_subprocess_denied:<entrypoint>
```

This means the current runtime path does not allow child process creation.

Normal module render and actions should not call `subprocess` directly. Use `sdk.tasks.run_subprocess(...)` so the runtime enters a task context with subprocess execution enabled and injects the sandbox environment into the child process.

Engines and extractors enable subprocess execution only in install-oriented phases. Runtime phases should not depend on spawning arbitrary child processes unless that runtime path explicitly supports it.

## Network Target Missing

Error shape:

```text
network_target_missing
```

This means the network guard received an empty target. Check the URL or host value before the call. Do not treat this as an approval problem; there is no valid target to approve.

## External URL Locked

Common response:

```text
External URL is locked.
```

This means the target was not allowed by the active sandbox policy, session approval, or permanent approval.

Check:

1. Is this target a stable dependency?
2. If yes, declare it in the correct manifest or phase.
3. If no, call `sdk.access.check_external_access(...)` and let the approval flow register a pending request.
4. If it was previously denied, an administrator must change that decision before the same structured subject/resource/operation/target will be allowed.

For stable module dependencies:

```json
{
  "access": [
    {
      "resource_type": "network",
      "operation": "receive",
      "target": "https://api.example.com/v1/reports"
    }
  ]
}
```

For stable engine or extractor dependencies:

```json
{
  "runtime": {
    "access": [
      {
        "resource_type": "network",
        "operation": "receive",
        "target": "https://api.example.com/v1/models"
      }
    ]
  }
}
```

## Approval Does Not Work

Approvals are authorized by the access-policy service, not by the module call site.

A user can manage external access only when:

- a runtime user is present
- the user is not scoped to an organization for this decision
- the user has a super role or super access level

If approval raises `external_access_admin_required`, the current runtime user is not authorized to approve or deny the resource.

Session approval also needs a session key. If there is no session key, `approve_for_session(...)` is skipped.

## OS Network Enforcement Still Blocks

If Python-level checks allow a target but Linux egress still fails, inspect the OS-level layer.

Check:

1. `sandbox.os.enabled` is enabled only when you intend process-level egress filtering.
2. The helper is running and reachable through `sandbox.os.helper_socket`.
3. The policy file exists at `sandbox.os.policy_file`.
4. The policy file is owned by the application user and is not group- or world-writable.
5. The host resolves to concrete IP addresses.
6. The destination port is the one declared or approved.
7. The target process is in the cgroup managed by the helper.

With default paths, same-host instances do not share the helper socket or policy file. Their cgroups and iptables chains are also process-specific, using names derived from the process identifier. Policy file collisions and iptables chain replacement between instances should not happen unless deployment config overrides make two instances share the same `sandbox.os.policy_file`, `sandbox.os.helper_socket`, or process-specific network enforcement target.

In same-machine multi-instance deployments, verify that custom `sandbox.os.policy_file` and `sandbox.os.helper_socket` values are unique per running application process unless the deployment deliberately serializes and owns that sharing.

In multi-node deployments, also check that `network.stream.type` uses a provider that reaches every node. With the in-memory stream provider, approval refresh events do not cross process boundaries.

Enable OS sandbox debug output when diagnosing helper and allowlist flow:

```bash
DEMOCRAI_DEBUG_OS_SANDBOX_FLOW=1
```

For media and external-access checks, this debug flag can also be useful:

```bash
DEMOCRAI_DEBUG_MEDIA_FLOW=1
```

## Declaration Checklist

| Runtime path | Check this first |
|---|---|
| Module render/action/command | module `manifest.json` |
| Module task | same module `manifest.json` |
| SDK task subprocess | same module `manifest.json` and subprocess helper usage |
| Engine runtime | engine manifest `runtime` section |
| Engine install | engine manifest `install` section |
| Extractor runtime | extractor manifest `runtime` section |
| Extractor install | extractor manifest `install` section |
| MCP | registered MCP endpoint and approval state |

If the resource is expected and stable, declare it narrowly. If it is dynamic, use approval. If neither is true, keep it blocked.
