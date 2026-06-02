# Auth: Tokens

## `AuthSDK`

`AuthSDK` is the request-scoped auth facade exposed as `module_sdk.auth`.

Its job is deliberately small:

- keep token creation behind a supported module-safe boundary
- centralize the logic used to rebuild the current session token
- avoid forcing modules to import low-level auth internals directly

The class is bound to the active SDK instance, so all session-aware behavior comes from the current request context and current SDK session.

## `create_token(data: Dict[str, Any], expires_delta: Any | None = None) -> str`

Use this method when your module needs to issue an access token from a payload that is already known, validated, and appropriate for the runtime.

That last point matters.

This method does not inspect the payload and decide whether it is semantically correct for your use case. It is a thin, supported wrapper around the core token generator. In other words:

- it encodes what you pass
- it does not fetch missing user data for you
- it does not validate that you chose the right claims for the application flow

That is why this method belongs in trusted server-side flows only.

This method is not an audit or telemetry API. It only creates the token. Authentication audit events are emitted by the core auth layer during the login flow or current-session token refresh.

### Why use it

Use `create_token(...)` instead of importing the core JWT helpers directly when:

- the module has already built the canonical claims payload
- a trusted auth transition flow needs to issue a token from already-authoritative claims
- you want the module code to stay on the SDK boundary

Do not use it as a shortcut for "I need user information". If the real need is "authenticate this username/password pair", use `login(...)`. If the real need is "rebuild the current authenticated token from authoritative profile data", use `refresh_current_session_token()` instead.

### What the payload should contain

In this codebase, the canonical token shape built by auth flows contains at least:

- `sub`
- `user_id`
- `role`
- `access_level`
- `organization_id`

If your flow is meant to produce a normal authenticated user token, stay aligned with that shape.

### Example

```python
token_payload = {
    "sub": str(user_id),
    "user_id": user_id,
    "role": role,
    "access_level": resolved_access_level,
    "organization_id": organization_id,
}

token = module_sdk.auth.create_token(token_payload)
```

## `login(username: str, password: str) -> dict[str, Any]`

Use this method from the login action when the module needs to authenticate a username/password pair.

This method delegates the actual login attempt to the core auth layer. The core layer owns:

- login rate-limit state
- credential verification
- authoritative user profile lookup
- token payload construction
- token creation and validation
- auth audit events

On success, the method returns:

- `ok: True`
- `token`
- `token_payload`
- `user_info`
- `user_id`

On failure, it returns:

- `ok: False`
- `type: "error"`
- `error`
- `details`

The module action should use this result to update the session and return UI effects. It should not write audit records and should not perform a second credential verification.

### `refresh_current_session_token() -> dict[str, Any]`

This is the method to use when the current authenticated session already exists, but the module needs a fresh JWT that reflects the current authoritative user profile.

This is the safer and more application-aware method compared with `create_token(...)` because it does not trust the caller to prepare the canonical claims manually.

Instead, it re-derives them from the auth layer.

The core auth layer records the token-refresh audit event as part of this operation. Module code should consume the returned token payload and should not write audit records itself.

### Why use it

Use `refresh_current_session_token()` when:

- the user is already authenticated
- a module flow needs to reissue the current session token
- role, organization, or access-level data may have changed
- you want the token rebuilt from authoritative profile information

### Return shape

On success, the method returns:

- `ok: True`
- `token`
- `token_payload`
- `user_id`

On failure, it returns:

- `ok: False`
- `type: "error"`
- `error`
- `details`

Treat this as structured application data, not as a bare token call.

### Real project example

The auth module exposes a `refresh_token` action that uses this method directly:

```python
refreshed = module_sdk.auth.refresh_current_session_token()
if not bool(refreshed.get("ok")):
    return refreshed

token = refreshed["token"]

return module_sdk.effects.respond(
    module_sdk.effects.set_jwt(token)
)
```
