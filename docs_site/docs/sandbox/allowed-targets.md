# Sandbox Allowed Targets

## What an Allowed Target Means

An allowed target is a network pattern that the active runtime subject is expected to reach for a declared operation.

For modules, the canonical manifest declaration is the structured `access` list.

```json
{
  "name": "reports",
  "access": [
    {
      "resource_type": "network",
      "operation": "receive",
      "target": "https://api.example.com/v1/"
    },
    {
      "resource_type": "network",
      "operation": "send",
      "target": "https://storage.example.com/upload"
    }
  ]
}
```

For engines and extractors, stable access is also declared as structured access rules for the phase that needs them:

```json
{
  "runtime": {
    "access": [
      {
        "resource_type": "network",
        "operation": "receive",
        "target": "https://api.example.com/v1/"
      }
    ]
  },
  "install": {
    "access": [
      {
        "resource_type": "network",
        "operation": "receive",
        "target": "https://files.pythonhosted.org"
      }
    ]
  }
}
```

Engine install phases also include the default Python package download hosts used by the runtime.

## Matching Rules

Network checks support URL-style and endpoint-style patterns.

Examples:

| Declaration | Allows |
|---|---|
| `https://api.example.com/v1/reports` | that HTTPS URL |
| `https://api.example.com` | HTTPS requests to that host |
| `api.example.com` | socket or URL checks that resolve to that host |
| `api.example.com:443` | that host on port `443` |
| `uploads.example.com:443` | that subdomain on port `443` |

For URL checks, the matcher first compares URL patterns. It then falls back to host/port endpoint matching. For socket checks, it compares host and port directly.

`localhost`, `127.0.0.1`, and `::1` are treated as equivalent for matching.

When the target is an IP literal and the pattern is a hostname, the matcher may resolve the hostname and compare the resulting IPs. DNS results are cached briefly in the running process.

Use the narrowest stable target that covers the dependency. Prefer a concrete HTTPS origin or API path over broad host patterns.

## Sources of Allowed Targets

Allowed network targets can come from several places:

- module `manifest.json` through structured `access` entries
- engine and extractor manifests through phase-specific structured `access` entries
- engine runtime configuration through manifest-declared `allowed_config_urls`
- MCP runtime endpoints derived from the configured MCP server URL
- runtime media/external URL flows that create a policy context for a specific URL
- session or permanent access-policy approvals
- OS-level allowlist sources when the Linux OS sandbox is enabled

Module-level targets are read from the registered module. The module runtime, module task runtime, and SDK task helpers all pass those targets into the guard.

Tool, agent, and pipeline definitions can also declare allowed network targets and filesystem paths. Those declarations are attached to the AI runtime asset definition. Do not treat them as module sandbox allowlist entries unless the runtime path you are using explicitly consumes those fields. For ordinary module execution, the enforced module network allowlist comes from `manifest.json`.

## Declaration Locations

| Subject kind | Where to declare stable network access | Where to declare stable filesystem access | Sensitive imports |
|---|---|---|---|
| Module | top-level `access` entries with `resource_type=network` | top-level `access` entries with `resource_type=filesystem` | top-level `allowed_imports` in `manifest.json` |
| Module task | same module `manifest.json` | same module `manifest.json` | same module `manifest.json` |
| SDK task subprocess | same module `manifest.json`, injected into child env | same module `manifest.json`, injected into child env | not inherited through a manifest field in the child env |
| Engine runtime | `runtime.access` entries, plus manifest-declared config URL targets when configured values should be allowed | `runtime.access` filesystem entries | `runtime.allowed_imports` |
| Engine install | `install.access` entries plus runtime default installer hosts | `install.access` filesystem entries plus install runtime paths | `install.allowed_imports` |
| Extractor runtime | `runtime.access` network entries | `runtime.access` filesystem entries | `runtime.allowed_imports` |
| Extractor install | `install.access` network entries | `install.access` filesystem entries plus install runtime paths | `install.allowed_imports` |
| MCP | derived from the configured MCP server endpoint | no subject filesystem paths | none |

## Allowlist Versus Approval

A manifest allowlist entry means the developer intentionally made that resource part of the subject's runtime contract.

An approval means an administrator or authorized runtime user allowed a resource that was not already part of that contract.

Those two mechanisms should not be used interchangeably:

- use allowlists for expected dependencies known before deployment
- use approvals for resources discovered at runtime or chosen by a user/admin
- use denial when a requested target should remain unavailable even if requested again

If a module always needs `https://api.example.com`, declare it. If a user pastes an arbitrary webhook URL, check access and let the approval flow decide.
