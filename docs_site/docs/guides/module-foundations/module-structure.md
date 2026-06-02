# Module Structure

Use this structure for a Python module that owns UI, actions, optional models,
tools, agents, skills, and translations.

```text
modules/<module>/
  __init__.py
  manifest.json
  rbac.json
  models.py
  locales/
    en.json
    it.json
    fr.json
    es.json
    de.json
    zh.json
  actions/
    __init__.py
    *.py
  ui/
    __init__.py
    index.py
    ...
  utils/
    actions/
    ui/
      yaml/
  agents/
  tools/
  skills/
```

Keep UI structure in YAML under `utils/ui/yaml/`. A view should load YAML,
read only the data it needs, and seed data or page/global store values with
`builder.set_data(...)` or `builder.set_store(...)`.

Module-owned tables are declared in `models.py` from the SDK database boundary.
Do not create `migrations/`, `env.py`, or `versions/` by hand during skeleton
work. Define models first, then generate data migrations through the core
autogenerate command for the module.

Use `locales/<lang>.json` for visible strings. YAML can reference translations
with `@t/<key>`, while Python uses `sdk.i18n.t("<key>")`.
