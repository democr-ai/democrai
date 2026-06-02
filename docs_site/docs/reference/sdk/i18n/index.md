# SDK Domain: `i18n`

## Overview

The `i18n` domain is the SDK surface modules use to resolve the effective user language and translate server-side strings from Python code.

At first glance it looks small, but it does more than just call a translator.

It also applies the runtime conventions that matter for module authors:

- translation keys are expected to be fully qualified
- the effective language is resolved from explicit override, session state, or user profile

That combination is why `module_sdk.i18n` is the correct entry point for module code instead of calling the translation service directly.

## What This Domain Is For

Use `sdk.i18n` when your module needs to:

- render translated text in Python code
- interpolate translated strings with runtime values
- resolve the effective language for the current or a specific user
- make locale-aware decisions in actions, render functions, or helpers

If the text lives in YAML UI bindings, the SDUI translation syntax can handle that directly.

If the text is produced in Python, especially in actions and server-side render code, `module_sdk.i18n` is the intended abstraction.

## The Public Surface

The facade is intentionally compact:

- `get_user_language(...)`
- `t(...)`

That small surface is enough because most module localization needs reduce to two questions:

1. what language should I use?
2. what is the translated value for this key in that language?

## Mental Model

The easiest way to reason about this domain is:

- `get_user_language(...)` answers the language-selection question explicitly
- `t(...)` answers the translation question and can also infer the language if you do not pass one

If you keep those responsibilities separate, the API becomes straightforward.

## Subsections

This domain is split into focused pages:

- Language Resolution
- Translating Keys

That split matches how developers usually work with localization in module code: first understand which language is in effect, then translate fully qualified keys.
