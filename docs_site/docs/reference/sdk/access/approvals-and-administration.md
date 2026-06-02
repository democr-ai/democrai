# Access: Approvals and Administration

## `approve_for_session(...)`

Use this when you want to allow a resource only for the current session scope.

This is the right choice when:

- the approval should not outlive the current session
- you are validating something temporary
- you want a cautious workflow before granting a permanent approval

Example:

```python
sdk.access.approve_for_session(
    resource_type=sdk.access.EXTERNAL_RESOURCE_NETWORK,
    operation="receive",
    target="https://example.com/data.json",
    session_key=session.get("session_key"),
)
```

In practice, this is useful for flows like:

- "allow this import source for this session"
- "temporarily allow this binary while debugging"
- "approve this exact path just for the current operator session"

If your module keeps an in-memory set of session approvals, pass it as `session_approvals` so the same request cycle can see the new approval immediately.

The approving user is not supplied by the module. It is resolved from the active runtime context, the same way external access checks resolve the current requester.

Authorization is also enforced there. If the current runtime user is not allowed to manage external access, the service rejects the operation instead of trusting the module call site.

Session approval requires a pending request for that same session. If the pending request has no `session_key`, session approval is not valid; use permanent approval or deny the request.

The approval must match the pending request operation. For example, approving `operation="receive"` for a network target does not approve `operation="send"` for the same target.

## `approve_permanently(...)`

Use this when the approval should be persisted and reused later.

This is the method for explicit long-term approval, usually from an admin or review flow.

Example:

```python
sdk.access.approve_permanently(
    resource_type=sdk.access.EXTERNAL_RESOURCE_SYSTEM_DEPENDENCY,
    operation="execute",
    target="pdftotext",
)
```

This is appropriate when the organization has already decided that a resource is acceptable and the approval should survive the current session.

Use it sparingly. Permanent approval is a policy decision, not just a convenience toggle.

The approving user is resolved from the active runtime context. The service also validates there that the current user is allowed to manage external access, instead of trusting module code to pass the right actor.

Approving a request does not automatically restart the blocked operation unless the pending request was created with `resume_action`. Requests without resume metadata only update access state.

When a pending request has `resume_action`, approval triggers that action with the original requester context, not with the administrator context. The action receives the decrypted resume context as its `ctx`.

## `deny_external_access(...)`

Use this when you want to persist a denial for an external resource.

That matters when you want the system to remember that a request was reviewed and rejected, instead of leaving it in a generic "not approved yet" state.

Example:

```python
sdk.access.deny_external_access(
    resource_type=sdk.access.EXTERNAL_RESOURCE_FILESYSTEM,
    operation="read",
    target="/mnt/shared/private.xlsx",
)
```

This is typically used in approval-review interfaces, not in ordinary module execution.

As with approvals, the acting user is resolved from the runtime context and authorization is enforced inside the external access service itself.

## `is_permanently_approved(...) -> bool`

This is a direct lookup for persisted approval state.

Use it when you specifically care about permanent approval and do not need the fuller logic of `check_external_access(...)`.

## Administration Helpers

Use the remaining administration-oriented helpers when the module is building approval-management interfaces rather than ordinary runtime checks:

- `can_manage_external_access(...)`
- `sync_session_external_approvals(...)`

These helpers matter most in review, moderation, admin, and settings flows.

## Module-Level Pending Request Helper

`democrai.sdk.access.get_pending_external_access_requests()` returns pending
external access requests for approval administration screens.

Example:

```python
from democrai.sdk.access import get_pending_external_access_requests

pending = get_pending_external_access_requests()
```

This is a module-level helper, not a method on `module_sdk.access`. Use the
facade methods for request checks, approvals, denials, and session approval
synchronization.
