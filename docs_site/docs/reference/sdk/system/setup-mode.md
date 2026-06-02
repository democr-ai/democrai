# Setup Mode

This section covers the most privileged part of the domain:

- `module_sdk.system.setup.is_enabled()`
- `module_sdk.system.setup.finalize(admin_user, admin_pass, admin_email=None)`
- `module_sdk.system.setup.request_finalize(admin_user, admin_pass, admin_email=None, stream_id=None, session_key=None)`

This subdomain is not general operational sugar. It is specifically about the application setup flow.

## `setup.is_enabled() -> bool`

This method returns whether setup mode is currently enabled.

Example:

```python
if module_sdk.system.setup.is_enabled():
    module_sdk.system.log("Application still in setup mode")
```

### What It Is For

Use it when UI or action logic needs to branch on whether the application has already completed setup.

That is how it is used in setup pages and some guarded UI flows.

### What It Actually Does

The method checks `app_ctx().setup_mode` and returns `False` if even that lookup fails.

So it is intentionally forgiving and safe for normal UI logic.

### Important Detail

This helper reads the same setup-mode flag used by the setup finalization path. It is intentionally a simple runtime-state check, not a full validation of whether a submitted setup payload is complete.

## `setup.finalize(admin_user, admin_pass, admin_email=None) -> None`

This method finalizes setup mode, bootstraps the runtime around the chosen configuration, runs migrations, seeds the admin user, and then disables setup mode.

Example:

```python
module_sdk.system.setup.finalize("admin", "change-me", admin_email="admin@example.com")
```

### What It Is For

Use this only in the actual setup-completion flow, after configuration has already been written and validated.

The `system` module setup helper is the reference pattern around this operation:

1. build or validate the config payload
2. apply it to the config provider
3. save the config
4. ensure setup storage is writable
5. log setup progress
6. request setup finalization through `module_sdk.system.setup.request_finalize(...)`

Direct `finalize(...)` is the low-level finalization routine behind that flow.

### What It Actually Does

The method performs a lot of runtime work.

At a high level, it:

1. checks that `context.setup_mode` is truthy
2. tears down and resets existing database/data-engine globals
3. rebuilds the persistence, media, KG, vector, data, and observability providers from config
4. resets the network session store when available
5. runs database and storage migrations
6. seeds the administrator user
7. tries to apply process restrictions such as seccomp/Landlock if enabled
8. finally sets `context.setup_mode = False`

This is much more than “mark setup as complete”.

### Important Preconditions

If the application is not in setup mode, the method raises:

```text
PermissionError("APPLICATION NOT IN SETUP MODE")
```

That means it is intentionally protected from accidental use in normal runtime flows.

### Why This Matters

This is an orchestration API, not just a flag flip.

If you call it from the wrong place or at the wrong time, you are not merely making a harmless state change. You are reinitializing core runtime providers and executing migrations.

So the right way to document and use it is:

- setup flow only
- after config persistence and validation
- with clear operator intent

## `setup.request_finalize(...) -> dict[str, Any]`

This method queues setup finalization through the core runtime consumer.

Example:

```python
result = await module_sdk.system.setup.request_finalize(
    "admin",
    "change-me",
    admin_email="admin@example.com",
    stream_id=ctx.get("stream_id"),
    session_key=ctx.get("session_key"),
)
```

### What It Is For

Use it when setup completion should be requested asynchronously and tracked by the runtime instead of running the full finalization inline inside the action.

The optional `stream_id` and `session_key` let the runtime associate setup progress and follow-up messages with the active client/session.

### Relationship To `finalize(...)`

`request_finalize(...)` does not replace `finalize(...)` as the low-level finalization routine.

It publishes a setup-finalize request that the core runtime consumes, and the consumer eventually runs the same setup-finalization path.

## Real Usage Pattern

The existing setup helper does roughly this:

```python
cfg = app_ctx().config
apply_config_payload(cfg, payload)
cfg.save()
ensure_setup_storage_writable(cfg)

module_sdk.system.log("[Setup] Configuration saved. Bootstrapping providers...", "info")
await module_sdk.system.setup.request_finalize(
    admin_user,
    admin_pass,
    admin_email=admin_email,
    stream_id=stream_id,
    session_key=session_key,
)
module_sdk.system.log("[Setup] Finalization requested.", "info")
```

That is the pattern module authors should follow if they are touching the setup flow itself.

## Practical Guidance

Treat `setup.finalize(...)` as one of the most privileged SDK methods in the project.

For normal module development, you will almost never need it.

For setup-flow work, you should document and structure the surrounding code so it is obvious that configuration save, storage checks, and setup finalization happen in the correct order.
