# SDK Domain: `effects`

## Purpose

`sdk.effects` is the domain actions use to tell the client or runtime what should happen next.

This is one of the most important SDK domains because it is the main bridge between server-side work and client-visible behavior.

Actions do not usually mutate the UI directly.
They return effect payloads, and the runtime/client applies those effects.

That means `sdk.effects` is not just a convenience API. It is the response contract of the action system.

Use it when your module needs to:

- navigate to another route
- request a render
- show a notification
- replace the client JWT
- request a clipboard or browser window action
- send targeted UI protocol messages instead of rerendering the whole page
- update already-connected clients through a live stream
- ask the connected client for current store, data-model, or component runtime state
- build drawer or modal surface payloads
- trigger a runtime-side pipeline or confirmation flow

## Mental Model

There are three distinct patterns in this domain, and keeping them separate makes the API much easier to use correctly.

### 1. Return effects from an action

This is the normal case.

### 2. Return raw UI protocol messages as one effect

Use `ui_messages(...)` when the right result is one or more direct A2UI messages.

### 3. Publish updates to a live stream

Use the `publish_*` helpers when the original action has already returned but connected clients still need updates.

### 4. Ask the current client for runtime state

Use the `ask_current_*` helpers inside async actions when the server needs the current client-held state before deciding the next update.

## In This Section

- [Response and Navigation](response-and-navigation.md)
- [UI Messages and Patching](ui-messages-and-patching.md)
- [Streams and Runtime Effects](streams-and-runtime-effects.md)
