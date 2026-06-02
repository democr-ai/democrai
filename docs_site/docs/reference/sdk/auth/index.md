# SDK Domain: `auth`

## Purpose

`sdk.auth` is the authentication-facing SDK domain for module code.

This domain is intentionally narrow. It is not the full authentication subsystem of the application, and that is by design. Module code should not reach into low-level JWT helpers, role-normalization logic, or auth-service internals directly when the SDK already exposes the supported boundary.

In practice, `sdk.auth` serves two different needs:

- module code that must issue or refresh a token in a controlled server-side flow
- action code that must declare permission requirements through `permission_required(...)`

Those are related, but not identical.

The first is runtime token handling.
The second is authorization metadata for actions.

If you keep those two roles separate while reading the API, the domain becomes much easier to use correctly.

## Mental Model

The easiest way to think about `sdk.auth` is this:

- `module_sdk.auth.create_token(...)` issues a JWT from a payload you already trust
- `module_sdk.auth.login(...)` runs the core username/password login flow
- `module_sdk.auth.refresh_current_session_token()` rebuilds and reissues the token for the current authenticated session user
- `from democrai.sdk.auth import permission_required` declares which permissions an action requires
- `from democrai.sdk.auth import public` declares that an action is callable before login

Most modules will use only one of these patterns:

1. decorate actions with `@permission_required([...])`
2. call `module_sdk.auth.login(...)` from the login action
3. refresh the current token after a login or profile update flow

Actions are private by default for unauthenticated requests. Mark an action with `@public` only when it is intentionally callable by guests, such as a login action.

Direct token creation is a more specialized operation. Use it when the flow genuinely needs to issue a token, not as a generic convenience wrapper.

Auth audit events are not written through the SDK. Login verification and token refresh telemetry are produced by the core authentication layer.

## In This Section

- [Tokens](tokens.md)
- [Action Authorization](action-authorization.md)
