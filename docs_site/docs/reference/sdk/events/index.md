# SDK Domain: `events`

## Overview

The `events` domain is the SDK surface modules use to work with the application-level module event system.

Its purpose is simple: let one module announce that something meaningful happened, and let other modules react to that event without creating direct imports or tight coupling between those modules.

That makes `sdk.events` one of the cleanest coordination tools in the SDK when the relationship between modules is "I want to react when this happens" rather than "I need to call your code directly".

## What This Domain Is Not

This domain is not the same thing as:

- UI events such as button clicks
- observability/audit event storage
- websocket stream publishing
- agent listener events inside `sdk.ai`

`sdk.events` is specifically about the module event system backed by:

- event slot declarations
- event listener registrations
- the shared module event dispatcher

If you are trying to notify the client UI, use `sdk.effects`.

If you are trying to observe runtime telemetry, that is a different system.

If you want modules to react to each other in a decoupled way, this is the correct domain.

## The Three Pieces You Need To Understand

The event system makes sense only when you see its three pieces together:

1. an event slot declares the contract
2. one or more listeners subscribe to that contract
3. some action, command, or runtime flow emits the event

The `Events` facade exposes the module event methods and a small runtime stream surface:

- `qualify_event_name(...)`
- `get_event_slots(...)`
- `emit(...)`
- `subscribe_stream(...)`
- `unsubscribe_stream(...)`

The business event surface is intentionally small. Event declaration and listener registration happen through decorators, while the runtime-facing operations happen through `sdk.events`.

The stream methods are for runtime channels that already exist inside the application, such as installer output streams. They are not a replacement for business module events and should not be used to create hidden cross-module contracts.

## When To Use This Domain

Use `sdk.events` when:

- your module completes a business event that other modules may care about
- you want extension points without direct module imports
- you want a stable event contract that can be inspected and subscribed to
- you want to emit a module-scoped event from an action or command

Typical examples:

- `auth` emits a login success event
- another module listens to that event to initialize user-specific state
- a commerce module emits `order.completed`
- an analytics or CRM module listens and reacts

## Mental Model

The most important idea is that event names are part of the module contract.

An event producer is not just "sending a dict". It is emitting a named contract that other modules may depend on. That is why event slots exist and why the SDK gives you `qualify_event_name(...)` instead of leaving naming entirely ad hoc.

If you use this domain well:

- event names stay stable
- payload shape is documented
- listeners remain decoupled from producers
- modules can extend each other without direct imports

## Subsections

This domain is split into focused pages:

- Event Names and Contracts
- Emitting Events
- Listener Execution and Runtime Behavior

Read them in that order if you are implementing a new cross-module event flow from scratch.

