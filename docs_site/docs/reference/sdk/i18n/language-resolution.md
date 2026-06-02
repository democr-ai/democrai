# Language Resolution

This section covers the method modules use when they need to know which language should be treated as effective for a user:

- `get_user_language(...)`

## `get_user_language(user_id: int | None = None) -> str`

This method returns the preferred language for a user.

Example:

```python
lang = module_sdk.i18n.get_user_language()
```

Example with an explicit user id:

```python
lang = module_sdk.i18n.get_user_language(user_id=42)
```

## What It Is For

Use this when your module needs a language code as data, not just a translated string.

Typical cases:

- choosing locale-dependent business behavior
- passing a language to an external integration
- storing a language-dependent preference
- branching on user language before building a response

This is different from `t(...)`, which is primarily about translating a specific key.

## How It Resolves The User

The method first normalizes the optional `user_id` argument.

If you pass a valid explicit user id, that id is used.

If you omit it, the method falls back to the current session user id from `sdk.session`.

If no user id can be resolved from the session, it falls back to `0`.

That detail matters because the translation service treats unresolved users as a default-language case rather than as a hard failure.

## What It Returns

The method delegates to the translation service’s `get_user_language(...)` and always returns a string.

If the runtime cannot resolve a user-specific language, the fallback is `"en"`.

### Important Detail

This SDK facade returns the service result as-is, only wrapped as `str(...)`.

That means normalization such as lowercasing is not guaranteed by `get_user_language(...)` itself.

If your downstream logic needs normalized casing, normalize it explicitly:

```python
lang = module_sdk.i18n.get_user_language().strip().lower()
```

The codebase already does this in places where stable lowercase values matter.

## Why You Would Use It Instead Of Reading Session Data Directly

A common temptation is to read:

```python
session["user"]["language"]
```

directly and stop there.

That is weaker than using `get_user_language(...)` because:

- session shape may not be the only source of truth
- the runtime translation layer already knows the fallback rules
- explicit user lookup should remain centralized

Using the facade keeps language resolution aligned with the rest of the application.

## Real Usage Pattern

The `auth` module uses `module_sdk.i18n.get_user_language(user_id)` during login to resolve the language that should be stored into the authenticated session payload.

That is a good example because it shows the method being used as a source of user preference data, not just as a convenience around translation.

## What This Method Does Not Do

It does not:

- load module locale files
- translate keys
- apply interpolation context

Those concerns belong to `t(...)`.

Use `get_user_language(...)` when you need the language code itself.

