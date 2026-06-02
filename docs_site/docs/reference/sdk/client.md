# SDK Domain: `client`

## Purpose

`democrai.sdk.client` is the runtime-entry domain that exposes the request-scoped SDK object and its proxy helpers.

Normal module code should usually work through:

- injected `module_sdk` / `sdk` function arguments in actions, tools, and agents
- domain imports such as `from democrai.sdk.decorators import action`

Use `democrai.sdk.client` directly when you specifically need the active request-scoped SDK proxy outside those injected call sites, for example in render modules or helper code.

## Public Objects

### `SDK`

The concrete root SDK object bound to:

- `module_name`
- `module_path`
- `current_path`
- `session`

It assembles the runtime domains:

- `access`
- `ai`
- `auth`
- `database`
- `decorators`
- `dependencies`
- `effects`
- `engines`
- `environment`
- `events`
- `extractors`
- `hooks`
- `i18n`
- `knowledge`
- `media`
- `models`
- `pages`
- `system`
- `tasks`
- `ui`

### `current_sdk`

Context variable storing the SDK instance active for the current request.

### `active_sdk`

Proxy that resolves attributes from:

- the current request-scoped SDK when available
- the default core SDK otherwise

This is the supported way to access the active SDK object outside an injected handler argument.

## Example

```python
from democrai.sdk.client import active_sdk as sdk


async def render(params: dict, session: dict):
    builder = sdk.ui.load("ui/yaml/tickets_list")
    return builder
```

## Practical Notes

- Treat `sdk.client` as runtime plumbing, not as the main place to discover business capabilities.
- Prefer domain imports such as `democrai.sdk.decorators`, `democrai.sdk.auth`, `democrai.sdk.database`, and `democrai.sdk.effects` for normal module authoring.
- Use the `active_sdk` proxy only when there is no injected `module_sdk` argument available.

