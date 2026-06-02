# Translating Keys

This section covers the main translation method of the domain:

- `t(...)`

This is the method most module authors will use constantly in render functions, action handlers, form builders, helper utilities, and server-side UI composition.

## `t(key: str, context: dict | None = None, lang: str | None = None) -> str`

This method translates a fully qualified key using the current SDK language context.

Example:

```python
title = module_sdk.i18n.t("system.user.list.title")
```

Example with interpolation:

```python
message = module_sdk.i18n.t(
    "system.role.update.not_found",
    context={"role_id": role_id},
)
```

Example with explicit language override:

```python
text = module_sdk.i18n.t("chat.shell.empty", lang="it")
```

## What It Is For

Use this for user-facing strings produced in Python code.

Typical examples:

- titles and labels built in render functions
- toast and notification messages in actions
- dynamic form labels and validation messages
- server-side strings that need interpolation with runtime values

This is the standard localization path for Python module code.

## What It Does Internally

The facade does two important things before translation:

1. it resolves the effective language using the SDK-level precedence rules
2. it calls the translation service with the key, resolved language, and optional interpolation context

Only then does it call the translation service with:

- the key
- the resolved language
- the optional interpolation context

The SDK facade does not prepend the current module name. Pass stable, fully qualified keys such as `system.user.list.title`.

## Language Precedence

Inside the `I18n` facade, the language used by `t(...)` follows this precedence:

1. explicit `lang`
2. `session[SessionKey.USER_LANGUAGE]`
3. language resolved from the authenticated session user
4. otherwise no explicit lang is passed, so the translation service falls back to its own default-language behavior

This is the real runtime behavior of the facade, and it is worth understanding because it means `t(...)` does not always perform the same kind of lookup as `get_user_language(...)`.

For example:

- if you pass `lang="FR"`, that value is used directly
- if the session already contains a language, that wins
- if not, the method may ask the translation service for the session user’s language
- if even that does not apply, the translation service default language takes over

## Key Resolution Behavior

The translation service resolves keys with a fallback order:

1. requested language
2. system default language
3. English
4. key itself

Use stable module-prefixed keys consistently in code.

## Interpolation With `context`

When you pass `context`, the translation service applies Python `str.format(...)` interpolation to the translated value.

Example:

```python
module_sdk.i18n.t(
    "system.user.update.not_found",
    context={"user_id": user_id},
)
```

### Important Behavior

If formatting fails, the translation service returns the untranslated template value rather than raising.

That means bad interpolation keys do not usually crash the request, but they do leave you with partially broken user-facing text.

So treat interpolation mistakes as real bugs even though the runtime is permissive.

## Real Usage Patterns

This method is used everywhere in the codebase for:

- UI labels in the `system` module
- dynamic page titles and subtitles
- notification and toast messages in actions
- model and engine management forms
- chat shell and chat detail strings

That broad usage is a good signal: `t(...)` is the default localization tool for Python-side module code.

## A Practical Example

Imagine you are building an action that deletes an entity and needs to show a localized toast.

The pattern looks like this:

```python
return module_sdk.effects.respond(
    module_sdk.effects.notify(
        "toast",
        {
            "level": "success",
            "message": module_sdk.i18n.t(
                "system.model.toast.deleted"
            ),
        },
    )
)
```

Now imagine you need interpolation:

```python
detail = module_sdk.i18n.t(
    "system.role.update.title",
    context={"name": str(role.get("name") or "")},
)
```

These are the most common and correct usage patterns for module authors.

## When To Pass `lang` Explicitly

Pass `lang` only when the translation must deliberately ignore the current session/user language resolution path.

Typical cases:

- previewing content in another language
- generating text for a recipient whose language differs from the current session user
- admin tools that inspect translations across languages

For ordinary user-facing module flows, omitting `lang` is usually correct.

## Practical Guidance

Use:

- `module_sdk.i18n.t(...)` for Python-side user-facing strings
- `module_sdk.i18n.get_user_language(...)` when you need the language code itself
- YAML translation syntax for purely declarative SDUI strings

Do not bypass the facade unless you are working on the translation system itself.
