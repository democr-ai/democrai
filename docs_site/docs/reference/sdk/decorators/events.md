# Decorators: Events

## Event Decorators

The event decorators work similarly to the render-hook decorators, but for module events.

## `event_listener(name=None, priority=0)`

Use this to register an event listener callback.

### What it does

Like `render_hook(...)`, this decorator expects a **fully qualified event key**. If the key is invalid or not fully qualified, registration is skipped and a warning is emitted.

If valid, the listener is registered in the module event registry with:

- the event key
- the callback
- the priority
- the module name

### Why use it

Use this when your module wants to react to a named event emitted somewhere else in the runtime.

## `event_slot(name, params=None, optional=True, description="")`

Use this to declare that an event slot exists and what shape it expects.

### What it does

The decorator declares an event contract in the module event registry:

- slot name
- owning module
- expected params
- optionality
- description

Unlike `event_listener(...)`, this decorator is about defining the extension contract rather than attaching a listener implementation.

### Real project example

The auth module imports and uses `event_slot` in its actions layer, which is a good signal of the intended purpose: declaring a named event contract other parts of the system can target.

### Why use it

Use this when your module exposes an event hook point and wants to make that event discoverable and documented at the registry level.
