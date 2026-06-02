# Effects: Response and Navigation

## `respond(*effects)`

This is the standard response wrapper of the domain.

Most action handlers should return `module_sdk.effects.respond(...)`.

### What it does

It wraps one or more effect payloads into the canonical action response shape:

```python
{"effects": [...]}
```

### Example: toast + navigation

```python
return module_sdk.effects.respond(
    module_sdk.effects.notify(
        "toast",
        {"title": "Saved", "text": "Profile updated", "variant": "success"},
    ),
    module_sdk.effects.navigate("/system/user", render=True),
)
```

## `navigate(path, render=True)`

Use this when the correct UX outcome is "go to another route".

### Real project example

```python
return module_sdk.effects.respond(
    module_sdk.effects.navigate(conversation_path(str(conversation.id)), render=True)
)
```

Use `render=False` only when the surrounding UI flow already supports route change without full rerender.

## `render(path=None)`

Use this when the simplest correct outcome is a full rerender.

Typical cases:

- after CRUD flows where no stable incremental patch exists yet
- when the page derives its data from server render state
- when the page structure itself may change significantly

## `notify(channel, payload, user_id=None, organization_id=None)`

Use this when you want to emit a notification effect.

Example:

```python
return module_sdk.effects.respond(
    module_sdk.effects.notify(
        "toast",
        {
            "title": "Deleted",
            "text": "Ticket removed",
            "variant": "success",
        },
    )
)
```

### Real channel behavior

The effect facade accepts any string, but the request-cycle executor has concrete built-in behavior only for specific channels:

- `toast`
- `inapp`
- `in_app`
- `ws`
- `bus`
- `email`

For `toast`, the executor wraps the payload into an `eventNotification` message and defaults `kind` to `toast` if you did not provide it.

For unknown channels, the runtime logs a warning unless a custom notifier has been wired in separately.

That means `notify(...)` is not just "any arbitrary notification bus". If you are writing normal module code and you want a client-visible message, `toast` is the safest documented choice.

## `confirm(via="dialog", path=None, params=None, render=True)`

Use this when the client should enter a confirmation flow before continuing.
