# SDK Domain: `access`

## Purpose

`sdk.access` is the domain you use when a module needs to answer one of these questions:

- does the current user have the permissions required for this operation?
- can this subject perform a specific operation on an external network target, filesystem path, or system dependency?
- how do I approve or deny that access for the current session or permanently?

This page matters because these are two different concerns that often get mixed together:

- authorization inside the application
- approval of resources outside the application

The first is about permissions such as `system.user.view` or `reports.export`.
The second is about whether a module is allowed to reach something external such as:

- `https://api.example.com/data.json`
- `/usr/bin/pdftotext`
- `/mnt/shared/input.csv`

`sdk.access` gives you a single place for both, but you should think about them separately.

External access is operation-specific. A network `receive` approval does not allow network `send`, and a filesystem `read` approval does not allow `delete`.

## Mental Model

When you read the API, the easiest way to orient yourself is this:

- `check_permissions(...)` is a pure permission check
- `check_external_access(...)` is the main gate for external resources
- `require_external_access(...)` is the resumable gate for external work that can continue after approval
- `approve_for_session(...)` and `approve_permanently(...)` record approvals
- `deny_external_access(...)` records an explicit denial
- `is_permanently_approved(...)` is a direct lookup
- `can_manage_external_access(...)` tells you whether a user can administer approvals
- `sync_session_external_approvals(...)` keeps the runtime approval cache aligned after you change approvals

The `democrai.sdk.access` module also exposes
`get_pending_external_access_requests()` as a module-level helper for approval
administration code. It is not a method on `module_sdk.access`.

Most module code will only need:

1. a permission check before a sensitive action
2. an external access check before touching an external resource, including the required operation

The approval methods are usually used by admin flows, settings pages, or review actions that manage the approval lifecycle.

## In This Section

- [Permissions and Resource Types](permissions-and-resource-types.md)
- [External Access Checks](external-access-checks.md)
- [Approvals and Administration](approvals-and-administration.md)
