# Sandbox Access Policy Contract

This page is the source of truth for sandbox approval identity.

The approval contract is structured. It is not a string key assembled by joining unrelated values.

Every runtime approval decision is about this tuple:

```text
subject_type + subject_name + resource_type + operation + normalized_target + scope/session
```

If two requests have the same target but a different operation, they are different requests and must not collide.

## Subjects

The subject is the runtime actor that is trying to use the resource.

Supported subject types are:

- `module`
- `engine`
- `extractor`
- `agent`
- `tool`
- `pipeline`
- `core`

The subject name must be the real runtime name, not a convenient module fallback.

Examples:

```text
module:system
engine:whisper
extractor:yolo
agent:demo.reader_agent
tool:demo.read_file
pipeline:demo.document_pipeline
core:core
```

Do not record an engine, extractor, agent, tool, or pipeline request as `module:system` just because the system module initiated the flow. The approver must see the actor that will actually touch the resource.

## Resource Types

Current resource types are:

- `network`
- `filesystem`
- `system_dependency`

Do not use `url` as a resource type. URLs are network targets, not a resource type.

## Network Operations

Network access is operation-specific.

| Operation | Meaning | Typical examples |
| --- | --- | --- |
| `connect` | low-level connectivity where request direction is not known | socket connect, OS egress allowlist |
| `receive` | receiving data from a remote target | `GET`, `HEAD`, download, websocket receive |
| `send` | sending data to a remote target | `POST`, `PUT`, `PATCH`, `DELETE`, upload, websocket send |

Rules:

- `send` does not imply `receive`.
- `receive` does not imply `send`.
- OS-level network enforcement may only know `connect`.
- SDK HTTP helpers, proxies, and application network guards must use `receive` or `send` when the method is known.

Example:

```python
access = sdk.access.check_external_access(
    resource_type=sdk.access.EXTERNAL_RESOURCE_NETWORK,
    operation="receive",
    target="https://huggingface.co/acme/model",
)
```

## Filesystem Operations

Filesystem access is also operation-specific.

| Operation | Meaning | Typical examples |
| --- | --- | --- |
| `read` | read data or metadata | `open(..., "r")`, `stat`, `listdir`, `scandir`, `Path.read_text` |
| `create` | create a new file or directory | `mkdir`, exclusive create, new output file |
| `modify` | change an existing path | overwrite file, chmod, truncate, utime |
| `delete` | remove a path | unlink, rmdir, rmtree source side |
| `execute` | execute a binary or script | subprocess executable, `os.system`, asyncio subprocess |

Rules:

- `read` does not imply any write operation.
- `create` does not imply `modify`.
- `modify` does not imply `delete`.
- `execute` is separate from `read`; being able to read a binary does not mean the subject may run it.
- Composite operations must be checked explicitly. For example, `rename` has a source-side `delete` and a target-side `create` or `modify`.

Example:

```python
access = sdk.access.check_external_access(
    resource_type=sdk.access.EXTERNAL_RESOURCE_FILESYSTEM,
    operation="read",
    target="/mnt/imports/customer.csv",
)
```

## Manifest Shape

The canonical manifest shape is a flat `access` list.

```json
{
  "access": [
    {
      "resource_type": "network",
      "operation": "receive",
      "target": "https://huggingface.co"
    },
    {
      "resource_type": "network",
      "operation": "send",
      "target": "https://api.openai.com"
    },
    {
      "resource_type": "filesystem",
      "operation": "read",
      "target": "models/"
    },
    {
      "resource_type": "filesystem",
      "operation": "create",
      "target": "tmp/"
    }
  ]
}
```

The runtime normalizes each item to the same internal rule model used by approval checks.

There is no legacy adapter requirement for old approval keys. New manifests and tests should use the structured contract directly.

## Pending Requests

When a guarded operation is blocked and the call site registers a request, the pending request must preserve structured data:

```json
{
  "subject": {"type": "module", "name": "system"},
  "resource": {
    "type": "filesystem",
    "operation": "read",
    "target": "/mnt/imports/customer.csv"
  },
  "origin": {
    "user_id": 21,
    "session_key": "sess-21",
    "task_id": "task-123"
  },
  "resume": {
    "action": "system.resume_import",
    "context": "encrypted"
  }
}
```

The stored resume context is encrypted when present. Approval UIs must not depend on decrypted resume context.

## Scopes

Approval scope is part of the decision.

- `session`: valid only for the original session key.
- `permanent`: reusable for future checks of the same structured subject/resource/operation/target.
- `denied`: records that the request was reviewed and blocked.

Session approval is valid only when the pending request has a session key. Requests created by scheduled or long-running background work without a session can be approved permanently or denied, but not session-approved.

## UI Requirements

Approval UI must show:

- subject type and name
- resource type
- operation
- target
- whether a session key exists
- whether the request is resumable

Good labels:

- `Network receive`
- `Network send`
- `Filesystem read`
- `Filesystem delete`
- `Filesystem execute`

## No Legacy Keys

Do not use a string key such as:

```text
resource_type:module:target
```

That form cannot distinguish `send` from `receive`, or `read` from `delete`, and it hides the real runtime subject.

Use the structured fields as the source of truth.
