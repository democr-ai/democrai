# Access: External Access Checks

## `check_external_access(...)`

This is the main method of the domain.

Use it whenever a module is about to touch a resource that lives outside the normal application boundary.

That includes cases such as:

- downloading data from a remote URL
- reading a local or mounted filesystem path
- invoking a system tool that must be approved

Signature shape:

```python
access = sdk.access.check_external_access(
    resource_type=...,
    operation=...,
    target=...,
    register_request=True,
)
```

The important parameters are:

- `resource_type`: what kind of resource you are checking
- `operation`: what operation the subject wants to perform on that resource
- `target`: the concrete URL, filesystem path, or dependency name
- `register_request`: whether the check should also register a pending approval request when access is not already allowed

Common operation values:

```python
# download or GET/HEAD style access
operation="receive"

# POST/PUT/PATCH/DELETE/upload style access
operation="send"

# filesystem read
operation="read"

# filesystem create, update, delete, or execute
operation="create"  # or "modify", "delete", "execute"
```

Use `subject_type` and `subject_name` only when the real runtime subject is not the current module. For ordinary module code, the SDK defaults to `subject_type="module"` and the current module name.

The return value is an `ExternalAccessCheck`, not just a boolean. In normal module code you usually care about:

- `access.allowed`
- `access.requires_approval`
- `access.code`
- `access.message`

The most important practical point is still `register_request`.

If you are about to do real work and want the system to remember that approval is needed, leave it at the default `True`. If you only want to inspect current status without creating noise, pass `False`.

The other important practical point is what you do *not* pass anymore.

You do not tell the SDK:

- which user is making the request
- which session is active
- whether the resource is "already declared" and therefore safe

That information is resolved from the active sandbox and network policy context.

At runtime, the decision path now works like this:

- the current module name comes from the SDK unless you explicitly pass a different subject for a supported runtime actor
- user, organization, and session are read from the current network policy context
- the sandbox allowlist is read from the current process guard
- for nested runtimes such as `module -> engine -> mcp`, the check uses the runtime `subject_chain` and the `subject_allow_chain` recorded by the sandbox, not a boolean supplied by the caller

That matters because it keeps the source of truth inside the runtime guard. A module should not be able to bypass approval just by passing a convenient flag.

Example: checking access before fetching a remote feed

```python
access = sdk.access.check_external_access(
    resource_type=sdk.access.EXTERNAL_RESOURCE_NETWORK,
    operation="receive",
    target="https://example.com/data.json",
)

if not access.allowed:
    raise PermissionError(access.message)
```

Example: read-only status check without registering a new request

```python
access = sdk.access.check_external_access(
    resource_type=sdk.access.EXTERNAL_RESOURCE_FILESYSTEM,
    operation="read",
    target="/mnt/shared/input.csv",
    register_request=False,
)

if access.allowed:
    ...
```

Use that second style when rendering an admin UI or a diagnostics page where you want to show approval state without creating approval requests just by opening the page.

## `require_external_access(...)`

Use this method when blocked access should create a resumable approval request.

It performs the same runtime check as `check_external_access(...)`, but lets the caller attach a resume action and a small resume context to the pending request.

Signature shape:

```python
access = sdk.access.require_external_access(
    resource_type=sdk.access.EXTERNAL_RESOURCE_NETWORK,
    operation="receive",
    target="https://example.com/model.bin",
    resume_action="system.resume_model_materialization",
    resume_context={
        "available_model_id": 123,
        "catalog_id": "llama-3.2-3b-instruct-4bit",
    },
)
```

If access is already allowed, the method returns an allowed `ExternalAccessCheck` and no pending approval is needed.

If access is blocked, the runtime registers a pending request with the supplied resume metadata. The `resume_context` is serialized and encrypted before storage. Pending-request UIs should not display or depend on the decrypted context; it is intended only for the later resume executor.

Keep the resume context minimal. Store stable identifiers and enough information to restart the operation idempotently, not full payloads, credentials, tokens, or user-provided secrets.

### Resume contract

Automatic resume is opt-in.

A pending request is resumable only when `resume_action` is present. Approval of a request without `resume_action` only changes access state; it does not restart the caller.

When an administrator approves a resumable request, the runtime invokes `resume_action` as a normal action. The approval user is not reused as the caller. The resume action runs with a reconstructed request context from the original pending request:

- `requested_by` becomes the runtime user
- `organization_id` is restored when present
- `session_key` is restored when the original request had one
- `resume_context` becomes the action `ctx`

Use `resume_action` for work that can safely continue after an administrator approves the blocked resource, such as:

- model materialization after an external URL is approved
- importing a known file after a filesystem path is approved
- retrying a background task that was stopped by external access policy

Do not use `resume_action` for non-idempotent operations unless the resume action checks whether the work was already completed.

The resume action should receive stable identifiers from `resume_context` and reload current state from storage. Treat the context as a pointer to state, not as the state itself.

Resume execution is best-effort. If the resume action fails, approval still remains recorded and the failure is logged. The action should therefore be safe to run again from a retry button or background recovery flow.

Example: resumable background operation

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

The matching resume action should be idempotent:

```python
async def resume_catalog_model_download(ctx, sdk=None):
    catalog_model_id = ctx["catalog_model_id"]
    inventory_id = ctx["inventory_id"]

    inventory = load_inventory(inventory_id)
    if inventory.status == "ready":
        return {"status": "already_ready"}

    return await download_catalog_model(
        catalog_model_id=catalog_model_id,
        inventory_id=inventory_id,
        sdk=sdk,
    )
```

If the request is approved for a session, resume can only use that session when the original pending request had a `session_key`. Requests created by scheduled or long-running background work usually do not have a session; those requests can be denied or approved permanently, but should not be session-approved.
