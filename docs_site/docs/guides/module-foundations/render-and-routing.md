# Render and Routing

This guide covers the page-render contract for modules.

Module UI routes are Python modules under `modules/<module>/ui/...` with an async `render(...)` function. The router resolves the current path, imports the matching module, checks authentication and permissions, then calls `render(...)`.

## Basic Page

```python
from typing import Any
from democrai.sdk.client import active_sdk as sdk

async def render(params: dict, session: dict) -> Any:
    return sdk.ui.load("ui/yaml/index")
```

The render function should return a `Builder`. Keep layout in YAML whenever possible; use Python to load the YAML, prepare data, and set page or global store values.

## Public Pages

Pages require authentication by default. Add `@public` when a route must be reachable before login.

```python
from democrai.sdk.decorators import public, template
from democrai.sdk.client import active_sdk as sdk

@template("empty")
@public
async def render(params: dict, session: dict):
    return sdk.ui.load("utils/ui/yaml/login")
```

`@public` only removes the authentication requirement. It does not prevent authenticated users from opening the route.

## Guest-Only Pages

Use `@only_guest` for public pages that should only be rendered for unauthenticated users.

```python
from democrai.sdk.decorators import only_guest, public, template
from democrai.sdk.client import active_sdk as sdk

@template("empty")
@only_guest
@public
async def render(params: dict, session: dict):
    return sdk.ui.load("utils/ui/yaml/login")
```

When an authenticated session resolves a guest-only route, the router redirects to the authenticated home page. The target is resolved through `home_page(...)` registrations, not hardcoded by the page.

Use this for login-like pages. Do not use it for help pages, legal pages, or shared public content that authenticated users may still need to read.

## Templates

`@template(name)` marks which template should host the returned builder. It does not define the template.

```python
from democrai.sdk.decorators import template

@template("empty")
async def render(params: dict, session: dict):
    ...
```

Template providers are registered separately with `@ui_template(...)`.

## Home and Guest Entry Points

Modules can register canonical navigation entry points:

```python
from democrai.sdk.decorators import guest_page, home_page

@home_page("/auth/profile", priority=100)
def register_profile_home():
    pass

@guest_page("/auth/login", priority=100)
def register_login_guest_page():
    pass
```

These functions are registration markers. Their bodies are usually empty.

Runtime code should ask `module_sdk.pages` for these paths instead of hardcoding them:

```python
home_path = module_sdk.pages.get_home_path()
guest_path = module_sdk.pages.get_guest_path()
post_login_path = module_sdk.pages.get_post_login_redirect_path()
```

## Subsurface Routes

Some pages render into a named surface hosted by a shell page. This keeps navigation shells stable while the route-specific content is updated independently.

Use `prepare_shell_surface(...)` for the content route:

```python
async def shared_layout(builder):
    content_id = sdk.ui.prepare_shell_surface(
        builder,
        surface_id="module_content",
        shell_route="/module/shell",
        content_component_id="module_content_body",
    )
    return content_id, content_id
```

The shell route owns the matching `SurfaceHost`. The content route must keep the same `surface_id`; changing it breaks mounting.

## Related Reference

- [Decorators: UI and Pages](../../reference/sdk/decorators/ui-and-pages.md)
- [Pages SDK](../../reference/sdk/pages.md)
- [YAML Resources and Routing](../../reference/sdk/ui/yaml-resources-and-routing.md)
- [Shell Sections](../../reference/components/layout/shell-sections.md)
