# SDK Module: `normalize`

`democrai.sdk.normalize` reexports the platform normalization helpers that are
safe for SDK consumers to import directly.

These helpers are small value-normalization utilities. They do not perform
domain validation and they do not define persisted business contracts.

## Exports

Constants:

- `TRUE_STRINGS`
- `FALSE_STRINGS`

Functions:

- `normalize_bool(...)`
- `normalize_dict(...)`
- `normalize_float(...)`
- `normalize_int(...)`
- `normalize_key(...)`
- `normalize_list(...)`
- `normalize_string(...)`
- `normalize_string_list(...)`
- `os_key(...)`

## Usage

```python
from democrai.sdk.normalize import normalize_bool, normalize_string_list

enabled = normalize_bool(raw_enabled)
tags = normalize_string_list(raw_tags)
```

Use these helpers when the input shape is already expected to be loose, such as
configuration payloads or manifest-adjacent data.

Do not use them to hide unclear domain contracts. If a value is persisted or
drives domain behavior, the allowed shape should still come from the relevant
SDK model, schema, manifest, or domain helper.
