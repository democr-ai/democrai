# Listener Execution And Runtime Behavior

This section explains what happens after you emit an event.

Developers often understand how to declare a slot and how to call `emit(...)`, but the most important operational details live in the dispatcher behavior:

- how listeners are resolved
- what arguments listeners receive
- what happens if the payload does not match the slot contract
- what happens if no listeners exist
- what happens when a listener raises an error

Understanding these details makes the difference between "I can fire an event" and "I can design a reliable module extension point".

## Listener Registration

Listeners are registered through `@event_listener(...)`, not through the `Events` facade.

Example:

```python
@event_listener("auth.login.succeeded", priority=10)
async def on_login(user_id=None, role=None, session=None, module_sdk=None):
    ...
```

The important rule is that listeners should target the fully qualified event name.

The base registration helper rejects unqualified names. Scoped decorator binding can qualify names in some module-authoring paths, but for public SDK documentation the safe rule is still:

- producers may work with relative names
- listeners should subscribe to the fully qualified key

## How The Dispatcher Finds Listeners

When `module_sdk.events.emit(...)` forwards the event to the runtime dispatcher, the dispatcher:

1. reads the event definition, if one exists
2. loads the registered listeners for that exact event key
3. builds an SDK instance for each listener’s module
4. invokes each listener in registration order
5. collects all listener return values into a list

Each listener runs in the context of its own module SDK, not the producer module’s SDK.

That point is easy to miss, but it is extremely important.

If `auth` emits an event and `analytics` listens to it, the listener receives an SDK bound to `analytics`, not to `auth`.

That is exactly what you want, because the listener should operate as its own module, using its own models, effects, and helpers.

## What Parameters A Listener Can Receive

The dispatcher inspects the listener function signature and fills parameters by name.

The supported patterns are:

- `payload` receives the full payload dict
- `session` receives the event session
- `sdk`, `module_sdk`, or `democrai.sdk` receives the listener module SDK
- `event_name` receives the fully qualified event key
- any parameter whose name matches a payload key receives that payload value

That means all of these are valid styles:

```python
@event_listener("auth.login.succeeded")
async def listener(payload=None, module_sdk=None):
    ...
```

```python
@event_listener("auth.login.succeeded")
async def listener(user_id=None, role=None, session=None):
    ...
```

```python
@event_listener("auth.login.succeeded")
async def listener(event_name=None, module_sdk=None, organization_id=None):
    ...
```

### Why This Matters

Listeners do not need rigid boilerplate signatures. They can accept only the fields they care about.

That keeps listeners small and focused.

## Payload Validation Against Slots

If an emitted event has a declared slot, the dispatcher compares the payload against the declared `params`.

It warns when:

- declared params are missing from the emitted payload
- extra undeclared params are present in the emitted payload

These are warnings, not hard failures.

That behavior is deliberate: the runtime wants to surface contract drift without automatically crashing the producer flow.

### What This Means For Module Authors

You should still treat slot params as the real contract.

If the dispatcher warns that your event payload does not match the slot declaration, that is usually a documentation or contract problem that should be fixed, not ignored indefinitely.

## What Happens If No Slot Was Declared

If an event is emitted without a declared slot, the dispatcher logs a warning that the event was emitted without a declared public module API.

The event can still be delivered to listeners, but the platform is telling you that the event contract is under-specified.

In practical terms:

- undeclared events can work
- declared events are much easier to maintain

If an event is meant to be a stable extension point, declare the slot.

## What Happens If No Listeners Exist

If no listeners are registered for the emitted event:

- the dispatcher returns an empty result list
- it logs a warning if the event was expected to have listeners
- it does not warn when the slot is marked `optional=True`

This is why the `optional` flag on `@event_slot(...)` matters.

If your module is exposing an event as a hook that other modules may or may not implement, mark it optional.

If your architecture assumes that someone should always be listening, mark it non-optional so missing listeners become visible through warnings.

## What Happens If A Listener Raises

If a listener throws an exception, the dispatcher logs an error and returns `None` for that listener result instead of crashing the whole emission loop.

That is an important operational behavior:

- one broken listener does not prevent the dispatcher from continuing through the rest of the listeners
- producer code does not automatically fail just because one subscriber broke

### Why This Tradeoff Exists

The event system is designed for decoupled extensibility. In that kind of architecture, one subscriber should not usually be able to break the entire producer flow.

The cost of that design is that listener failures can become easier to miss if you are not watching logs or testing the flow carefully.

So the practical rule is:

- rely on the dispatcher to isolate listener failures
- still treat listener errors as real bugs that need to be fixed

## Return Value Semantics

The dispatcher collects one result entry per listener execution.

That means the result from `emit(...)` is a list in listener order. Entries may be:

- concrete listener return values
- `None` for listeners that returned nothing
- `None` for listeners that failed and were swallowed after logging

This makes the result useful for tests, because you can assert that the expected listeners ran and inspect what they returned.

## Practical Design Guidance

When you design a new event contract:

1. declare a slot
2. choose a stable, fully qualified business-oriented event name
3. keep the payload compact and explicit
4. mark the slot optional only when the architecture really supports "zero listeners"
5. make listeners idempotent where possible
6. do not treat event emission like synchronous RPC

That last point is especially important.

Events are best when they represent decoupled reactions to completed facts. If your producer strictly requires one specific listener to succeed, you may not actually want an event contract. You may want a direct call or another coordination mechanism.

