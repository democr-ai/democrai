# UI Platform

This package contains the internal UI runtime: render service, YAML builder,
tag/media helpers and hooks. Module UI should remain YAML first.

## Boundary

Modules:

- declare layout, components and bindings in YAML.
- use SDK UI/page/effects APIs.
- prepare minimal data in Python render functions.

Core UI platform:

- loads YAML.
- builds surface payloads.
- applies binding/data/store values.
- emits client messages.

Modules must not depend on `democrai.core.platform.ui` internals.

## Key Files

- `yaml_builder.py`: UI construction from YAML.
- `render_service.py`: page resolution and rendering.
- `media_sources.py`: UI media source resolution.
- `hooks.py`: internal UI hooks.
- `tags.py`: runtime tag helpers.

## YAML First

In modules:

- layout, components, bindings and visibility live in YAML.
- Python fetches data and populates `data`/`store`.
- avoid `get_component(...).set_property(...)` when a documented binding can
  express the value.
- drawers and modals use UI actions unless extra module logic is required.

## Data and Store

Use:

- data model for current surface data.
- page/global store for explicit UI state.
- action effects for incremental updates.

The UI must not invent persistent domain values. Capabilities, providers,
statuses and formats should come from SDK/domain contracts.

## Rules

- YAML for structure and bindings.
- Python only for minimal data and actions.
- No hardcoded domain logic in UI pages.
- Prefer small effects/streams over full rerenders when possible.
- Clients remain independent from the core package.
