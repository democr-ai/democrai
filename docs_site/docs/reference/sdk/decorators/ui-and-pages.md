# Decorators: UI and Pages

## `ui_template(name=None, priority=0)`

Use this to register a UI template provider in the shared template registry.

### What it does

The decorator resolves a name and registers the function in the template registry with the provided priority.

Priority matters when more than one template provider competes for the same template name.

This is the decorator that defines or overrides a template implementation.

If you omit `name`, the decorator auto-namespaces the registration using the module prefix and the function name. So a template provider inside `modules.demo...` can register as something like `demo.my_template` automatically.

### Why use it

Use this when your module provides a reusable template provider that the runtime can resolve by name.

If you register `@ui_template("full", priority=50)`, you are not saying "this page uses the `full` template". You are saying "this function is a provider for the template named `full`", and with sufficient priority it can override an existing implementation.

This is different from `template(name)`, which does not register a provider. `ui_template(...)` is the template definition side of the contract.

### Example

```python
from democrai.sdk.decorators import ui_template

@ui_template("chat.sidebar", priority=10)
async def chat_sidebar_template(session=None):
    ...
```

### Override example

Because registration is name-based and priority-aware, a module can override an existing template intentionally:

```python
@ui_template("full", priority=50)
async def custom_full_template(session=None):
    ...
```

That is a template-provider override, not a page-render annotation.

## `template(name)`

This is a render annotation, not a template-provider registration decorator.

### What it does

It marks the async function with `_template_name = name` and returns an async wrapper.

During page render resolution, the router/runtime checks that attribute and, if present, calls `builder.set_template(render._template_name)` on the builder returned by the page.

The same behavior is also applied in the module runtime render path, not only in the direct router path.

So the practical meaning is:

- `@ui_template(...)` defines a template implementation
- `@template(...)` declares which template a page render should use

### Why use it

Use `@template(...)` on a page `render(...)` function when that page should be mounted inside a specific template.

This is especially common for pages that should render inside a lightweight shell such as `empty`.

### Real project example

```python
from democrai.sdk.decorators import public, template

@template("login")
@public
async def render(...):
    ...
```

In the current codebase, the common pattern is:

```python
@template("empty")
@public
async def render(params: dict, session: dict):
    ...
```

That means:

- the page render is public
- the builder returned by `render(...)` should use the `empty` template

It does **not** define the `empty` template itself. That template is provided elsewhere through `@ui_template("empty")`.

## `public`

Use this to mark a page render callable as accessible without an authenticated user.

### What it does

The decorator attaches `_is_public = True` to the callable. During route resolution, the router checks that marker before deciding whether an unauthenticated session may render the page.

### Why use it

Use it on guest-facing routes such as login, setup, dependency warning, or other pages that must be reachable before a user session exists.

It does not mean "show this page only to guests". It only means "authentication is not required".

For guest-only behavior, combine it with `@only_guest`.

## `only_guest`

Use this to mark a public page render callable as guest-only.

### What it does

The decorator attaches `_only_guest = True` to the callable. During route resolution, if the current session is already authenticated and the target route is guest-only, the router redirects to the authenticated home page instead of rendering the guest page.

### Why use it

Use it for pages such as login or registration where an authenticated user should not stay on the guest flow.

This is intentionally separate from `@public`:

- `@public` allows unauthenticated access
- `@only_guest` redirects authenticated users away

Guest-only pages should normally use both.

### Example

```python
from democrai.sdk.decorators import only_guest, public, template
from democrai.sdk.client import active_sdk as sdk

@template("empty")
@only_guest
@public
async def render(params: dict, session: dict):
    return sdk.ui.load("utils/ui/yaml/login")
```

The authenticated redirect target is resolved through the application home-page registry, not hardcoded by the page.

## `home_page(path, priority=0)`

Use this to register the authenticated home page path for a module.

### What it does

The decorator registers `path` in the home-page registry and then returns the function unchanged.

The function body is not the important part here. The registration side effect is.

### Why use it

Use this when the module wants to declare:

"When the runtime asks for a home page for authenticated users, this path is a candidate."

## `guest_page(path, priority=0)`

This is the guest-user equivalent of `home_page(...)`.

Use it when the module wants to declare a landing path for unauthenticated or guest flows.

## `notification_center_view(path, priority=0)`

Use this to register the module route that should be opened as the notification-center view.

### What it does

The decorator registers `path` in the notification-center view registry with:

- the route path
- the priority
- the owning module name

The function body is not the important part. Like `home_page(...)` and `guest_page(...)`, this decorator is primarily a registration side effect.

### Why use it

Use it when a module provides the UI page for reviewing core notifications, such as sandbox external-access requests.

The core owns notification count, approval actions, and the registered view path. The module provides the page and can read notification items through `module_sdk.system.notifications`.

### Example

```python
from democrai.sdk.decorators import notification_center_view


@notification_center_view("/system/notifications", priority=0)
def register_notification_center_view():
    pass
```

## `render_hook(name=None, priority=0)`

Use this to register a render-hook handler.

### What it does

The decorator expects a **fully qualified hook key**. If the name is empty or not fully qualified, registration is skipped and a warning is emitted.

If the key is valid, the function is registered in the render-hook registry with:

- the hook name
- the handler
- the priority
- the owning module name

### Why use it

Use this when your module wants to contribute content or behavior to a named render-extension point rather than owning the whole render flow.

### Important practical point

This decorator is intentionally strict about fully qualified keys. That reduces collisions and ambiguity in cross-module extension points.

## `render_hook_slot(name, optional=True, description="")`

Use this to declare that a render-hook slot exists.

### What it does

The decorator declares a slot contract in the render-hook registry rather than registering a hook implementation.

That means:

- `render_hook(...)` provides an implementation
- `render_hook_slot(...)` declares the extension point

### Why use it

Use this when your module owns a render surface and wants downstream modules to be able to plug into it in a controlled way.

This is the right abstraction when a hook point is part of the module contract, not just an incidental internal detail.
