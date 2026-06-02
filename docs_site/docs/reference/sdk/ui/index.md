# SDK Domain: `ui`

## Overview

The `ui` domain is the main SDK entry point for building SDUI surfaces from module code.

It combines three things:

- wrapped component constructors
- the `Builder` API for assembling and serializing surfaces
- helper methods for YAML loading, resource resolution, media-safe sources, and routing-related UI work

This is the domain most module authors interact with when writing pages.

## Important Boundary

This section documents the `sdk.ui` facade and the builder/runtime helpers around it.

It does **not** try to re-document every individual component class such as `Text`, `Button`, `DataTable`, or `Sidebar`.

For those, use the dedicated components reference:

- [UI Components Overview](../../components/index.md)

That split is intentional. The `ui` domain documentation should teach you how to use the UI system; the components reference should teach you what each component accepts and renders.

## Mental Model

`module_sdk.ui` gives you two authoring styles that can be mixed:

1. YAML-first authoring via `load(...)` and `from_yaml(...)`
2. Python-first authoring via `Builder()` and wrapped component constructors

In practice, most module pages should stay close to this pattern:

1. load a YAML structure or start from a builder
2. seed initial data or store values
3. tweak a few components when needed
4. return the builder

That keeps render functions thin and makes the UI easier to maintain.

## What This Domain Exposes

At the facade level, `module_sdk.ui` exposes:

- wrapped public component constructors, such as `module_sdk.ui.Text(...)`
- `Builder`
- `resolve_route(...)`
- `resolve_resource(...)`
- `resolve_media_source(...)`
- `from_yaml(...)`
- `load(...)`
- `prepare_shell_surface(...)`
- `mount_shell_frame(...)`
- `nav_active_path_rule(...)`

At module level, `sdk.ui` also exposes:

- `Router`
- `publish_to_stream(...)`
- low-level symbols such as `Component`, `Condition`, `bound`, and literal/bound value helpers

Those are documented where they matter, but the normal module entry point remains `module_sdk.ui`.

## Subsections

- Builder and Surface Messages
- YAML, Resources, and Routing Helpers

