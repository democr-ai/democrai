# Sandbox and External Access

## Role of External Access

External access is the approval layer on top of sandbox policy.

The sandbox answers:

> Did the active runtime subject declare this filesystem or network resource as part of its allowed execution boundary?

External access answers:

> If it was not declared, has this exact subject/resource/operation/target been approved for this session or permanently by an authorized administrator?

Both checks are part of one flow. Network policy calls and SDK access checks use the access-policy service, and that service evaluates the active subject, the requested resource type, the requested operation, the normalized target, and the current session scope.

## Check Order

When `check_external_access(...)` evaluates a target, the effective order is:

1. setup-mode filesystem exception for the system module
2. target normalization and validation
3. active sandbox allowlist from the current subject chain
4. session approval for the current session key
5. permanent approval
6. recorded denial
7. optional pending request registration
8. denial response

For network targets, successful sandbox, session, or permanent approval checks can also record the observed runtime target and request an OS-level allowlist refresh when the Linux OS sandbox is enabled.

The approval key is not a string such as `resource_type:module:target`. The operation is part of the decision. A `network receive` approval does not allow `network send`, and a `filesystem read` approval does not allow `filesystem delete`.

## Checking Access in Module Code

Use `sdk.access.check_external_access(...)` when a module is about to use a resource that may not be declared in its manifest.

```python
access = sdk.access.check_external_access(
    resource_type=sdk.access.EXTERNAL_RESOURCE_NETWORK,
    operation="receive",
    target=user_supplied_url,
)

if not access.allowed:
    return {
        "ok": False,
        "message": access.message,
    }

# Perform the operation only after access.allowed is true.
```

The default `register_request=True` means a missing approval can create a pending request for administrators. Set `register_request=False` only for passive checks where creating an approval request would be noisy.

Supported resource types exposed through the SDK access facade are:

- `EXTERNAL_RESOURCE_NETWORK`
- `EXTERNAL_RESOURCE_FILESYSTEM`
- `EXTERNAL_RESOURCE_SYSTEM_DEPENDENCY`

Every external access call also requires `operation`.

Use:

- `connect`, `receive`, or `send` for `network`
- `read`, `create`, `modify`, `delete`, or `execute` for `filesystem`
- `execute` for `system_dependency`

For ordinary outbound HTTP calls made inside a guarded runtime, the network guard performs the same kind of check automatically. The explicit SDK check is useful when you want to inspect the result, show a controlled UI response, or request approval before attempting the actual operation.

## Who Can Approve

Approvals are not authorized by trusting module code. The service resolves the acting user from the current runtime/network policy context.

A user can manage external access only when all of these are true:

- a runtime user is present
- the user is not scoped to an organization for this decision
- the user has a super role or super access level

If those conditions are not met, approval and denial operations raise `PermissionError`.

## Session Approval

Use session approval when the resource should be available only for the current session.

```python
sdk.access.approve_for_session(
    resource_type=sdk.access.EXTERNAL_RESOURCE_NETWORK,
    operation="receive",
    target="https://api.example.com/v1/report",
)
```

The service resolves the session key from the runtime context unless one is explicitly passed. Session approval requires a pending request for that same session. If the original pending request has no session key, the request can be denied or approved permanently, but it cannot be session-approved.

Session approval is appropriate for interactive, user-driven access such as a one-off import URL or a temporary webhook target.

## Permanent Approval

Use permanent approval when the resource should become an accepted dependency for future checks.

```python
sdk.access.approve_permanently(
    resource_type=sdk.access.EXTERNAL_RESOURCE_NETWORK,
    operation="receive",
    target="https://api.example.com/v1/report",
)
```

Permanent approval is an administrative policy decision. It is not a replacement for declaring stable module dependencies. If a module always requires a target, prefer a structured `access` declaration in the module manifest so reviewers can see the dependency before runtime.

## Denial

Use denial when a requested resource should remain blocked.

```python
sdk.access.deny_external_access(
    resource_type=sdk.access.EXTERNAL_RESOURCE_NETWORK,
    operation="send",
    target="https://unapproved.example",
)
```

After a denial is recorded for the structured subject/resource/operation/target, future checks return a disabled-resource response instead of re-registering the same request as a normal pending request.

## Resumable Requests

Some blocked operations can continue automatically after approval. This is opt-in and requires `resume_action` on the pending request.

Use the SDK access facade when registering a resumable request:

```python
access = sdk.access.require_external_access(
    resource_type=sdk.access.EXTERNAL_RESOURCE_NETWORK,
    operation="receive",
    target=model_source_url,
    resume_action="system.resume_catalog_model_download",
    resume_context={
        "catalog_model_id": catalog_model_id,
        "inventory_id": inventory_id,
    },
)

if not access.allowed:
    raise PermissionError(access.message)
```

When an administrator approves a request with `resume_action`, the runtime invokes that action with the original requester context. The administrator is the approver, not the resumed caller.

The encrypted `resume_context` is decrypted only for the resume executor and passed as the action `ctx`. Keep it minimal and idempotent: store stable identifiers, not secrets or large payloads. The resume action should reload current state and return cleanly if the work already completed.

Approval of a request without `resume_action` only changes access state. It does not restart the blocked caller.

## Why Call Sites Should Not Precompute Policy

Most runtime subjects already execute inside a context that has:

- a subject identity
- an allowed path list
- an allowed target list
- a subject chain for nested runtimes
- request/session identity when available

Because of that, module code should not pass around a precomputed boolean such as "this target is already allowed" and treat it as authority. The authoritative decision belongs to the runtime guard and access-policy service.

This prevents module code from bypassing policy by supplying convenient flags. The service reads the current sandbox state, request context, session approvals, permanent approvals, and denials itself.

## Related SDK Reference

For the SDK facade and return shape, see:

- [Access Overview](../reference/sdk/access/index.md)
- [External Access Checks](../reference/sdk/access/external-access-checks.md)
- [Approvals and Administration](../reference/sdk/access/approvals-and-administration.md)
