# Sandbox Developer Quickstart

Use this page when you are building a module and need to decide where an allow entry or approval belongs.

## Stable External API

If the module always calls the same external API, declare it in the module manifest.

```json
{
  "name": "reports",
  "access": [
    {
      "resource_type": "network",
      "operation": "receive",
      "target": "https://api.example.com/v1/reports"
    }
  ]
}
```

Then make the HTTP call normally from module render, actions, commands, or tasks. The module runtime passes declared network access into the network guard.

Use a stable origin or path that is narrow enough to review. Do not wait for runtime approval for a dependency that is part of normal module operation.

## User-Supplied URL

If the user supplies the URL, do not add a broad manifest allowlist just to make development easy. Check access before using it.

```python
access = sdk.access.check_external_access(
    resource_type=sdk.access.EXTERNAL_RESOURCE_NETWORK,
    operation="receive",
    target=url_from_user,
)

if not access.allowed:
    return {"ok": False, "message": access.message}
```

With the default `register_request=True`, a missing approval can become a pending request for an authorized administrator.

Use session approval when the URL should work only for the current session. Use permanent approval only when the resource should become an accepted dependency for future checks.

Use `operation="send"` instead of `receive` when the URL will receive data from the application, such as a webhook POST or upload.

## Stable External File or Directory

If the module must read or write a known external path, declare it in structured filesystem `access` entries.

```json
{
  "name": "reports",
  "access": [
    {
      "resource_type": "filesystem",
      "operation": "read",
      "target": "/srv/democrai/reports"
    },
    {
      "resource_type": "filesystem",
      "operation": "create",
      "target": "/srv/democrai/reports/output"
    }
  ]
}
```

The filesystem guard uses root-prefix matching. A path is allowed when the concrete path is the declared root or is under that root.

Keep these entries narrow. Avoid broad roots such as `/`, `/home`, or a whole project checkout.

## Subprocess From a Module

Normal module render and action execution should not call `subprocess` directly. Use the SDK task helper:

```python
result = await sdk.tasks.run_subprocess(
    ["python", "-m", "reports_worker", "--input", input_path],
    cwd="/srv/democrai/reports",
)
```

The helper enters the module sandbox with subprocess execution enabled and injects the module access policy into the child environment. When `sandbox.os.enabled` is true, subprocess execution also passes through the sandbox launcher so supported OS-level filesystem rules can be applied before the command runs.

## Engine or Extractor Dependency

Engines and extractors do not use module access declarations. Declare access in the manifest section for the phase that needs it.

```json
{
  "runtime": {
    "access": [
      {
        "resource_type": "network",
        "operation": "receive",
        "target": "https://api.example.com/v1/models"
      },
      {
        "resource_type": "filesystem",
        "operation": "read",
        "target": "/srv/democrai/models"
      }
    ]
  },
  "install": {
    "access": [
      {
        "resource_type": "network",
        "operation": "receive",
        "target": "https://files.pythonhosted.org"
      },
      {
        "resource_type": "filesystem",
        "operation": "create",
        "target": "tmp/"
      }
    ]
  }
}
```

Install declarations apply to install work. Runtime declarations apply when the active engine or extractor is invoked.

## MCP Endpoint

MCP access is derived from the registered MCP server endpoint. The runtime allows that endpoint inside the MCP guard and checks external access before fetching or invoking MCP tools.

When managing MCP servers through the SDK model facade, the relevant fields are `name`, `transport`, `endpoint_url`, `enabled`, and `timeout_ms`.

```python
created = module_sdk.models.mcp_server_registry.create(
    {
        "name": "search-tools",
        "transport": "http",
        "endpoint_url": "https://mcp.example.com",
        "enabled": True,
        "timeout_ms": 15000,
    }
)
```

If the endpoint is not already allowed or approved, the MCP runtime uses the same access-policy flow as other network targets.

## Debugging a Denial

Start from the exact denial message and identify the active subject kind. For the full flow, see [Troubleshooting](troubleshooting.md).

If the target is stable, fix the manifest or phase declaration. If the target is dynamic, do not widen the manifest just to silence the error. Use the access-policy approval flow.
