# SDK Domain: `decorators`

## Purpose

`sdk.decorators` is the registration surface modules use to declare what they expose to the runtime.

This domain is different from domains such as `sdk.database`, `sdk.media`, or `sdk.auth`.

Those domains are about doing work at runtime.

This one is about declaring capabilities so the runtime can discover, route, schedule, render, or execute them later.

In practical terms, `sdk.decorators` is how a module says:

- these are my actions
- these are my commands
- these are my templates and pages
- these are my render hooks and event hooks
- these are my tools, agents, and pipelines

If you think of this domain as "the module's public runtime manifest, expressed in Python", you will use it correctly.

## Mental Model

The easiest way to read this domain is by grouping decorators by responsibility:

1. Action and callable registration
   These expose callables to the application runtime.

2. Command lifecycle registration
   These declare background or runtime-managed commands.

3. UI and page registration
   These declare templates, landing pages, and render-extension points.

4. Event registration
   These declare listeners and event slots.

5. Agent/runtime registration
   These declare tools, agents, and pipelines.

6. Markers and helpers
   These do not register runtime handlers by themselves, but attach metadata used by other runtime layers.

The second important mental model is this:

Most decorators in this domain do not execute the registered function when Python imports the module.
They register metadata in one of the runtime registries.

That means the decorator call is usually about declaration, not immediate execution.

## Naming and Module Prefixes

Many decorators in this domain auto-qualify names based on the module where the function or class lives.

So when you write:

```python
@action("start_chat")
async def start_chat(...):
    ...
```

inside a module named `demo`, the registered runtime name becomes:

```text
demo.start_chat
```

The same pattern applies to tools, agents, commands, and several other runtime assets.

This matters because:

- names stay module-qualified
- collisions are reduced
- the runtime can resolve ownership more cleanly

If you pass a fully qualified name yourself, the decorator generally preserves it instead of adding the prefix again.

## In This Section

- [Actions and Functions](actions-and-functions.md): `@action`, `@validate`, `@function`, `@public`
- [Commands](commands.md): `@callable_command`, `@scheduled_command`, `@long_run_command`, `@single_run_command`
- [UI and Pages](ui-and-pages.md): `@ui_template`, `@template`, `@public`, `@only_guest`, `@home_page`, `@guest_page`, `@render_hook`, `@render_hook_slot`
- [Events](events.md): `@event_listener`, `@event_slot`
- [Agent and Runtime Assets](agent-and-runtime-assets.md): `@tool`, `@agent`, `@pipeline`
- [Helpers and Notes](helpers-and-notes.md): `get_registry()`, `module_sdk.decorators`, practical guidance
