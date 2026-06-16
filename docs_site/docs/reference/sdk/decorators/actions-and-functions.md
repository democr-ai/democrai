# Decorators: Actions and Functions

## `action(name=None)`

This is the most important and most frequently used decorator in the domain.

Use it to register a function as a UI action callable by the runtime.

### Why use it

Use `@action(...)` when the function is meant to be triggered from:

- a button action
- an input change action
- a submit flow
- a route-driven runtime call
- a general client-to-server interaction in module UI

This is the standard way modules expose interactive server behavior.

### What it actually does

The decorator does two important things:

1. it registers the wrapped callable in the action registry under the resolved runtime name
2. it adapts the call so common action parameters can be injected from `ctx`, `session`, and `sdk`

That second point matters a lot.

If the runtime invokes the action in the standard shape `(ctx, session, sdk)`, the wrapper inspects the function signature and fills parameters like:

- `ctx`
- `session`
- `sdk`, `module_sdk`, or `democrai.sdk`
- individual named parameters present in `ctx`

It also sets the current request-scoped SDK context while the action runs.

That is why action handlers can be written in a relatively ergonomic style without manually unpacking every piece of context.

### Real project example

The codebase uses this pattern everywhere:

```python
from democrai.sdk.decorators import action

@action("start_chat")
async def start_chat(ctx: dict, session: dict, module_sdk):
    ...
```

and:

```python
@action("set_user_language")
async def set_user_language(ctx: dict, session: dict, module_sdk):
    ...
```

The decorator name is local to the module. UI components dispatch module actions with the fully qualified `module.action` name, for example a handler declared as `@action("start_chat")` in module `chat` is called from UI as `chat.start_chat`. See [Action Dispatch](../../components/action-dispatch.md).

### Example: parameter injection from `ctx`

Because the action wrapper maps known parameter names from `ctx`, an action like this:

```python
@action("save_profile")
async def save_profile(user_id: str, display_name: str, module_sdk):
    ...
```

can be called from a context that contains `user_id` and `display_name`, and the decorator wrapper will pass those values to the function automatically.

That is useful, but it is not magic. Keep action signatures readable and consistent with the actual client payload shape.

### When to use it

Use `@action(...)` for module behavior that is part of the interactive application runtime.

Do not use command decorators for something that is really a UI action. Do not register plain helper functions as actions just because they are convenient to call from Python.

If the function is an internal helper rather than a runtime action, leave it undecorated.

## `validate(schema, strip_extra=False)`

Use `@validate(...)` with `@action(...)` to validate the action `ctx` before the action body runs.

The schema must be a Pydantic `BaseModel` class. The action still receives the standard module action shape:

```python
async def handler(ctx: dict, session: dict, module_sdk):
    ...
```

`@validate(...)` does not change the action signature and does not inject fields as direct Python parameters. It validates the incoming client payload and passes a validated `ctx` to the action.

### Example: form payload

Forms submit their values under the form component id. If your form id is `login_form`, validate that object explicitly:

```python
from pydantic import BaseModel, Field, field_validator

from democrai.sdk.decorators import action, validate


class LoginFormPayload(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)

    @field_validator("username")
    @classmethod
    def clean_username(cls, value: str) -> str:
        username = value.strip()
        if not username:
            raise ValueError("username is required")
        return username


class LoginSubmitPayload(BaseModel):
    login_form: LoginFormPayload


@action("login_submit")
@validate(LoginSubmitPayload, strip_extra=True)
async def login_submit(ctx: dict, session: dict, module_sdk):
    credentials = ctx["login_form"]
    username = credentials["username"]
    password = credentials["password"]
    ...
```

### `strip_extra`

When `strip_extra=True`, fields sent by the client but not declared in the schema are removed before the action receives `ctx`.

This is intended to keep action code readable and avoid repeated defensive parsing such as `ctx.get(...) or ""`.

Runtime keys added by the core are preserved even when `strip_extra=True`:

- `_surface_id`
- `_source_component_id`
- `stream_id`
- `session_key`

The client cannot inject those keys through the action `context`; the request cycle owns them.

When `strip_extra=False`, validated fields are merged back into the original `ctx`, so undeclared client fields remain available.

### Validation failure

If validation fails:

- the action body is not called;
- the runtime returns a toast through UI messages;
- no notification queue entry is created.

Use validation for the boundary shape of the client payload. Do not use it to support multiple historical payload formats in the same action. If a component now submits through a form id, validate the form-id payload rather than legacy top-level fields.

## `function(name=None)`

Use this decorator to register a plain callable function in the SDK function registry.

This is a narrower and less common registration path than `@action(...)`.

### Why use it

Use `@function(...)` when the runtime should know about a callable, but the callable is not meant to be exposed as a normal UI action.

This is useful for internal runtime-discoverable functions or infrastructure-oriented callable surfaces where "action" would be the wrong abstraction.

### What it actually does

The decorator:

- resolves the module-qualified name
- registers the original function in the function registry
- returns a light wrapper that just calls the original function

Unlike `@action(...)`, this decorator does not perform action-style context argument injection.

That difference matters. If you need the standard module action call shape, use `@action(...)`, not `@function(...)`.

### Example

```python
from democrai.sdk.decorators import function

@function("reports.normalize_filters")
def normalize_filters(filters: dict) -> dict:
    ...
```

Use this only when the callable really belongs in a registry-visible function surface.

## `public`

`@public` is a metadata marker with two runtime meanings:

- on page render functions, it marks the route as publicly accessible without requiring an authenticated session
- on actions, it marks the action as callable by unauthenticated requests

### What it does

It marks the callable with public metadata inspected by the routing and action dispatch layers.

That means other runtime layers can inspect the function and treat it as public according to their own rules.

For page render functions, the router checks the public marker before deciding whether an unauthenticated session may render the page.

For actions, the dispatcher checks the public action marker before allowing a guest request to invoke the action. Actions are private by default. If an action is not marked public and the request has no authenticated user, the runtime rejects it before invoking the handler.

### Why use it

Use `@public` when a page render function or action should be reachable by guests or unauthenticated users.

This is commonly used for login routes, guest navigation, auth context bootstrap actions, and setup pages.

### Real project example

The auth and setup UI layers use patterns like:

```python
from democrai.sdk.decorators import public, template

@template("login")
@public
async def render(...):
    ...
```

and:

```python
@template("empty")
@public
async def render(params: dict, session: dict):
    ...
```

Those pages are intended to render before normal authenticated navigation is available.

Public actions use the same marker:

```python
from democrai.sdk.decorators import action, public

@action("login_submit")
@public
async def login(ctx: dict, session: dict, module_sdk):
    ...
```

### Important practical point

`@public` does not register the function in an action registry or page registry by itself. It only attaches metadata.

It also does not make a route guest-only. If authenticated users should be redirected away from the page, use `@only_guest` together with `@public`. The detailed UI/page behavior is covered in [Decorators: UI and Pages](ui-and-pages.md).

For actions, `@public` only controls guest access to the action itself. It does not replace route authorization, permission checks, input validation, or resource ownership checks.

## `setup_only`

`@setup_only` marks an action as callable only while the application is in setup mode.

Use it for setup wizard actions and setup finalization operations. Outside setup mode, the runtime rejects the action before invoking the handler.

```python
from democrai.sdk.decorators import action, setup_only

@action("setup_finish")
@setup_only
async def setup_finish(ctx: dict, session: dict, module_sdk):
    ...
```

`@setup_only` is intentionally separate from `@public`. A setup action should not stay available after setup has completed.

## `allow_public_upload`

`@allow_public_upload` marks a public or setup action as allowed to justify a deferred media upload from an unauthenticated client.

This decorator does not make an action callable by guests. It only adds upload-specific metadata inspected by the `/media/uploads/raw` endpoint when the request has no authenticated user.

Use it only on actions that genuinely consume an uploaded file before login or during setup, for example a setup configuration validation action.

```python
from democrai.sdk.decorators import action, allow_public_upload, setup_only

@action("validate_setup_config")
@allow_public_upload
@setup_only
async def validate_setup_config(ctx: dict, session: dict, module_sdk):
    ...
```

For authenticated users, normal action authorization is still the controlling check. The marker is only a guard against guests using unrelated public actions, such as login, as a pretext for storing files.
