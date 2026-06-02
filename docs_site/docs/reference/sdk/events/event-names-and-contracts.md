# Event Names And Contracts

This section covers the two methods developers usually need before emitting any event:

- `qualify_event_name(...)`
- `get_event_slots(...)`

It also explains how these methods relate to `@event_slot(...)` and `@event_listener(...)`, because the facade only makes sense in the context of those decorators.

## Relative Names vs Fully Qualified Names

In this SDK, event names are usually treated as module-scoped keys.

If your module is `auth` and you talk about `login.succeeded`, the fully qualified event name is usually:

```text
auth.login.succeeded
```

This is why the SDK exposes `qualify_event_name(...)`: module authors often want to work with the short relative name inside the producing module, while listeners in other modules usually subscribe to the fully qualified key.

## `qualify_event_name(name: str) -> str`

This method returns the fully qualified event name for the current SDK module.

Example:

```python
qualified = module_sdk.events.qualify_event_name("login.succeeded")
# -> "auth.login.succeeded"
```

### What It Is For

Use this method when you need the canonical event key rather than the short module-local name.

Typical cases:

- logging the exact emitted event name
- storing an event key in metadata or configuration
- building cross-module documentation
- checking that a listener is targeting the same key your module will emit

### How It Works

The method applies a simple rule:

- if the current module is `core`, it leaves the name unchanged
- if the name is already prefixed with the current module, it leaves it unchanged
- otherwise it prefixes the name with `<module_name>.`

That means:

```python
module_sdk.events.qualify_event_name("order.completed")
# "shop.order.completed"

module_sdk.events.qualify_event_name("shop.order.completed")
# "shop.order.completed"
```

### Why You Should Care

Without qualification rules, producers and listeners drift very quickly.

One module emits `login.succeeded`, another listens for `auth.login.succeeded`, a third listens for `login_success`, and now the contract is broken even though everyone thinks they are talking about the same business event.

`qualify_event_name(...)` helps keep the producer side deterministic.

## `@event_slot(...)` And Producer Contracts

Although `event_slot` is documented under the `decorators` domain, it is part of the practical event model and belongs in your mental model when using `sdk.events`.

An event slot declares:

- the event name
- the expected payload keys
- whether listeners are optional
- a human-readable description

Example from the real codebase:

```python
@event_slot(
    "login.succeeded",
    params=["user_id", "role", "organization_id"],
    optional=True,
    description="Triggered after a user successfully authenticates.",
)
def register_login_succeeded_event():
    return None
```

Because the slot is declared inside the `auth` module, the registered key becomes:

```text
auth.login.succeeded
```

### Why Slots Matter

You can emit events without a slot declaration, but the runtime will warn when an event is emitted without a declared public contract.

That warning exists for a reason: undeclared events are harder to discover, harder to document, and easier to break accidentally.

If an event is part of your module’s extension surface, declare a slot for it.

## `get_event_slots(module_name: str | None = None)`

This method returns the declared event slot definitions from the runtime registry.

Example:

```python
all_slots = module_sdk.events.get_event_slots()
auth_slots = module_sdk.events.get_event_slots("auth")
```

### What It Is For

Use this method when your module wants to inspect the event contracts currently registered in the application.

This is useful for:

- documentation pages
- developer tooling
- admin/debug interfaces
- validation that a target event contract exists

### What It Returns

The method returns the registry definitions for declared event slots.

In practice, each definition contains metadata such as:

- `name`
- `module_name`
- `params`
- `optional`
- `description`

This gives you the public contract for each declared event key.

### Filtering By Module

If you pass `module_name`, only definitions belonging to that module are returned.

If you omit it, you get all declared slots known to the runtime.

Example:

```python
for slot in module_sdk.events.get_event_slots("auth"):
    print(slot["name"], slot["params"])
```

### Why This Method Is Valuable

Event systems become opaque very quickly if modules emit arbitrary strings that nobody can discover.

`get_event_slots(...)` makes the public event surface inspectable at runtime. That is a major part of what turns the event system from a hidden implementation detail into a usable extension contract.

## `@event_listener(...)` And Name Matching

Listeners work differently from slots.

The listener decorator expects a fully qualified event name unless you are relying on scoped decorator binding behavior in very specific module authoring contexts. In the base helper, registration is skipped if the name is not fully qualified.

That means this is the safe pattern to document and use:

```python
@event_listener("auth.login.succeeded", priority=10)
async def on_login(...):
    ...
```

Not this:

```python
@event_listener("login.succeeded")
```

unless you are absolutely sure you are going through the scoped binding path that qualifies names for you.

For documentation aimed at SDK users, the important rule is:

- producers often work with relative names and `qualify_event_name(...)`
- listeners should subscribe to the fully qualified event key

## Practical Naming Guidance

Event names work best when they describe a completed domain fact, not a UI action.

Good examples:

- `auth.login.succeeded`
- `shop.order.completed`
- `crm.lead.converted`

Weak examples:

- `clicked_button`
- `save`
- `do_auth`

The better the event name reflects a domain fact, the easier it is for another module author to understand whether they should subscribe to it.

