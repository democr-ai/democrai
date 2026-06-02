# SDK Domain: `hooks`

## Overview

The `hooks` domain is the SDK surface modules use to work with render hooks.

Render hooks let one module declare a named UI insertion point and let other modules contribute components into that point without the slot owner depending on those modules directly.

This is one of the cleanest extensibility mechanisms in the SDK for UI composition.

## What This Domain Is For

Use `sdk.hooks` when your goal is:

- make part of a page extensible by other modules
- discover which render-hook slots are publicly declared
- resolve the UI fragments contributed to a specific slot

This domain is not about client-side events or runtime message streams.

If you need cross-module reaction to a business event, use `sdk.events`.

If you need to update the client UI after an action, use `sdk.effects`.

If you need one module to inject UI into another module’s render tree, use `sdk.hooks`.

## The Three Pieces Of The Hook System

Like the events domain, render hooks make sense only when you see the whole contract:

1. a slot owner declares a render-hook slot
2. one or more provider modules register hook callbacks
3. the slot owner resolves the hook at render time

The `Hooks` facade itself exposes only three methods:

- `qualify_render_hook_name(...)`
- `get_render_hook_slots(...)`
- `resolve_render_hook(...)`

Declaration and provider registration happen through decorators. Runtime lookup and resolution happen through `sdk.hooks`.

## Mental Model

A render hook is not a generic callback list. It is a named public UI extension point.

That means a good hook design has:

- a stable hook name
- a clear owner module
- a predictable location in the page layout
- a well-understood params contract

If that contract is clear, downstream modules can extend the page without the owner module hardcoding knowledge of who those downstream modules are.

## Subsections

This domain is split into focused pages:

- Hook Names and Slots
- Resolving Hook Content
- Provider Callbacks and Runtime Behavior

That ordering matches the real authoring flow: declare the extension point, resolve it where needed, then understand what provider callbacks can return and how the runtime normalizes those results.

