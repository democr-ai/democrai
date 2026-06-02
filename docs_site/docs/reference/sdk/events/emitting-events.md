# Emitting Events

This section covers the main operational method of the domain:

- `emit(...)`

If `qualify_event_name(...)` is about naming and `get_event_slots(...)` is about discovering contracts, `emit(...)` is the method that actually makes the event system do work.

## `emit(name: str, payload: dict | None = None, session: dict | None = None)`

This method emits a module event through the shared runtime dispatcher after qualifying the event name with the current module prefix.

Example:

```python
await module_sdk.events.emit(
    "login.succeeded",
    payload={
        "user_id": 42,
        "role": "admin",
        "organization_id": 7,
    },
    session=session,
)
```

### What It Is For

Use this when your module has completed a meaningful business event and wants other modules to be able to react to it.

This usually happens inside:

- actions
- commands
- runtime orchestration helpers

The most common pattern is: do the business work first, then emit the event once the business fact is true.

### What It Actually Does

`emit(...)` performs two important steps:

1. it converts the provided name into the fully qualified event key for the current module
2. it forwards the event to the shared runtime dispatcher `emit_module_event(...)`

So if the current module is `auth`, this call:

```python
await module_sdk.events.emit("login.succeeded", payload={...})
```

effectively emits:

```text
auth.login.succeeded
```

### Why You Should Use It Instead Of Calling The Dispatcher Directly

This facade exists so modules do not need to import the low-level dispatcher directly.

Using `module_sdk.events.emit(...)` gives you:

- module-aware name qualification
- a consistent request-scoped SDK surface
- a clearer contract in module code

If you skip the facade and call the lower-level dispatcher yourself, you take on naming responsibility manually and you lose the clarity of the SDK boundary.

## Real Example: Authentication Success

The `auth` module uses the event domain in a realistic way after a successful login.

The flow is:

1. verify credentials
2. resolve user info
3. update the session
4. create the JWT
5. emit `login.succeeded`
6. return effects for render/module refresh/JWT update

That ordering is correct because the event represents a completed fact: the user successfully authenticated and the new session state is already in place.

The actual emit pattern looks like this:

```python
await module_sdk.events.emit(
    "login.succeeded",
    payload={
        "user_id": user_id,
        "role": role,
        "organization_id": organization_id,
    },
    session=session,
)
```

This is a strong example because:

- the event name is domain-oriented
- the payload contains the core facts listeners need
- the event is emitted only after the login succeeded

## Payload Design

The payload should contain the business facts listeners need, not the entire internal state of the producing module.

A good payload is:

- explicit
- stable
- reasonably small
- focused on facts that other modules can use

For example, for a login event, these fields make sense:

- `user_id`
- `role`
- `organization_id`

What usually does not make sense:

- the whole session object
- raw UI state
- internal temporary variables that listeners should not depend on

### Why Stable Payloads Matter

If other modules subscribe to your event, the payload becomes part of your module’s extension contract.

That means you should think about payload shape with the same discipline you would apply to an API response. It does not need to be overdesigned, but it should be intentional.

## The `session` Argument

`emit(...)` accepts an optional `session` argument.

If you omit it, the method uses the current SDK session.

If you pass it explicitly, that session is forwarded to listeners instead.

### When To Pass It Explicitly

In actions and flows where you are already mutating the request session and want listeners to see the updated session immediately, passing the explicit `session` object is the safest and clearest choice.

That is exactly what the `auth` module does in the login flow.

### When The Default Is Fine

If your module is not doing anything special with session state and the current SDK session is already the one listeners should observe, omitting the argument is fine.

## Return Value

`emit(...)` returns the list of listener results returned by the dispatcher.

In many module flows, you can safely ignore that result.

But it is still useful in:

- tests
- debugging
- special coordination flows where listener return values are meaningful

Example:

```python
results = await module_sdk.events.emit(
    "inventory.synced",
    payload={"count": 12},
)
```

### Practical Advice

Treat the return value as optional operational feedback, not as the primary product of the event system.

The main purpose of event emission is side-effectful decoupled coordination, not RPC-style request/response.

## When To Emit

Emit the event only after the business fact it represents is true.

Good:

- after a user is actually logged in
- after an order is actually completed
- after a record is actually created

Weak:

- before the operation finishes
- before persistence happens
- before the session or state that listeners depend on is updated

If you emit too early, listeners react to a future that has not happened yet.

## Runtime Stream Subscription

The `events` domain also exposes two lower-level methods for subscribing to runtime streams:

- `subscribe_stream(stream_id)`
- `unsubscribe_stream(stream_id, queue)`

These methods are for module helpers that need to observe a shared runtime stream without importing core internals directly.

Typical use case: a background task starts an engine installation, subscribes to the engine-install output stream, filters messages for its `event_id`, and relays selected lines to `module_sdk.tasks.emit_progress(...)`.

```python
queue = module_sdk.events.subscribe_stream("system.engine.install.events")
try:
    payload = queue.get_nowait()
    if payload.get("event_id") == event_id:
        await module_sdk.tasks.emit_progress(
            task_id,
            0.60,
            label=payload.get("line"),
        )
finally:
    module_sdk.events.unsubscribe_stream("system.engine.install.events", queue)
```

Keep these subscriptions scoped and always unsubscribe in a `finally` block.

Do not use runtime streams for durable business facts. For those, define an event slot and emit a module event with `emit(...)`.
