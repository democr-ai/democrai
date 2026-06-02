# Auth: Action Authorization

## `permission_required(permissions)`

This decorator belongs to the `sdk.auth` module namespace, but it is not a method on `module_sdk.auth`.

You use it like this:

```python
from democrai.sdk.auth import permission_required
```

and then decorate actions:

```python
@action("send_chat_message")
@permission_required(["chat.access"])
async def send_chat_message(ctx: dict, session: dict, module_sdk):
    ...
```

This is one of the most common auth-related entrypoints used in modules, so it deserves to be documented here even though it is technically not a method of `AuthSDK`.

### What it does

`permission_required(...)` marks an action function with the permissions it requires.

It does not perform the full enforcement itself inside the decorator body. Instead, it attaches permission metadata to the wrapped function so the runtime can enforce authorization at the correct integration point.

That distinction matters.

The decorator is about declaring the contract:

"This action requires one or more of these permissions."

The actual enforcement happens in the application auth/runtime flow, not as ad hoc logic inside every action.

### Why use it

Use `@permission_required([...])` when:

- an action should not be callable by every authenticated user
- the module wants permission requirements to be explicit and discoverable
- you want to rely on the standard runtime enforcement path

This is better than sprinkling manual permission checks through action bodies because:

- the requirement is visible at the action definition
- the runtime can inspect it consistently
- the module keeps authorization policy close to the action contract

### Real project examples

The codebase uses this pattern heavily. For example:

```python
from democrai.sdk.auth import permission_required
from democrai.sdk.decorators import action

@action("start_chat")
@permission_required(["chat.access"])
async def start_chat(ctx: dict, session: dict, module_sdk):
    ...
```

and:

```python
@action("create_user")
@permission_required(["system.user.create"])
async def create_user(ctx: dict, session: dict, module_sdk):
    ...
```

### What it does not do

Do not treat `permission_required(...)` as a substitute for every runtime access decision in your module.

It does not:

- replace external resource approval checks
- validate arbitrary business rules inside the action body
- magically infer the correct permission for you

It declares action authorization requirements. That is its job.

## `public`

`@public` marks an action as callable without an authenticated user.

Actions are private by default: if a request has no authenticated user, the runtime rejects the action unless it is explicitly marked public or setup-only.

Use `@public` only for entrypoints that must work before login, such as login or guest navigation helpers.

```python
from democrai.sdk.auth import public
from democrai.sdk.decorators import action

@action("login_submit")
@public
async def login(ctx: dict, session: dict, module_sdk):
    ...
```

You can also import `public` from `democrai.sdk.decorators`. In that namespace it is shared with page routing metadata, so it marks both public page render functions and public actions.

Do not use `@public` as a shortcut for missing permissions. An authenticated action with no `@permission_required(...)` is still not guest-callable unless it is marked public.

## `setup_only`

`@setup_only` marks an action as callable only while the application is running in setup mode.

This is for setup wizard actions and finalization flows that should not remain callable after setup has completed.

```python
from democrai.sdk.decorators import action, setup_only

@action("setup_finish")
@setup_only
async def setup_finish(ctx: dict, session: dict, module_sdk):
    ...
```

`setup_only` does not mean "public forever". Outside setup mode the runtime rejects the action, even for authenticated users.
