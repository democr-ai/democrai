# SDK Domain: `pages`

## Overview

The `pages` domain is small, but it solves an important problem cleanly:

it lets modules ask the application which canonical page path should be used for common navigation entrypoints instead of hardcoding routes.

That matters because paths such as “home”, “guest landing”, or “post-login redirect” are application-level decisions. If module code hardcodes those assumptions, it drifts away from the actual shell behavior.

## Mental Model

`module_sdk.pages` is not a routing engine and it is not a page registry browser.

It is a thin facade over the core home/navigation resolution helpers.

Today it exposes three methods:

- `get_home_path()`
- `get_guest_path()`
- `get_post_login_redirect_path(session=None)`

All three are about one thing: “what path should the application use here?”

## `get_home_path() -> str`

This method returns the canonical authenticated home-page path.

Example:

```python
home_path = module_sdk.pages.get_home_path()
```

### What It Is For

Use it when an authenticated flow needs to navigate the user to the application home page without assuming what that page is.

Typical examples:

- a module action that wants to send the user back to the home page after completing a workflow
- a setup or onboarding flow that wants to land on the current authenticated entrypoint
- a generic “Back to home” action that should follow the same rule as the shell

### What It Actually Does

The method delegates directly to the core resolver:

```python
core.application.home.resolve_home_page_path()
```

That means the returned value is whatever the application currently considers the authenticated home page, not what the module happens to guess.

## `get_guest_path() -> str`

This method returns the canonical guest landing path.

Example:

```python
guest_path = module_sdk.pages.get_guest_path()
```

### What It Is For

Use it when your module needs to route an unauthenticated user to the application’s guest entrypoint.

Typical examples:

- redirecting to the public landing page after logout
- sending an unauthenticated user to the correct guest entry instead of assuming a fixed public route

### What It Actually Does

The method delegates directly to:

```python
core.application.home.resolve_guest_page_path()
```

So the module stays aligned with the shell’s current guest-page rule.

## `get_post_login_redirect_path(session=None) -> str`

This method resolves the path the application should open after login.

Example using the current SDK session:

```python
target = module_sdk.pages.get_post_login_redirect_path()
```

Example using an explicit session payload:

```python
target = module_sdk.pages.get_post_login_redirect_path(session=refreshed_session)
```

### What It Is For

Use it when your module is involved in authentication or session-refresh flows and wants to compute the same post-login target the core application would choose.

This is the most important method in the domain, because “where should the user land after login?” is exactly the kind of rule that tends to be duplicated incorrectly when modules hardcode paths.

### What It Actually Does

The method delegates to:

```python
core.application.home.resolve_post_login_redirect_path(...)
```

If you pass an explicit `session`, that session is used.

If you do not pass one, the method uses the current SDK session:

```python
session or self.sdk.session
```

### Why The Optional `session` Matters

This is useful when the flow has already computed or refreshed a session payload and wants to resolve the redirect target against that updated state instead of the original SDK session snapshot.

That makes the method especially appropriate in login and token-refresh flows.

## Practical Guidance

Use `module_sdk.pages` whenever the question is:

- “what is the right canonical app page here?”

Do not use it for:

- resolving dynamic route params
- rendering routes
- inspecting page definitions

Those concerns belong to the routing/UI layer, not this domain.

