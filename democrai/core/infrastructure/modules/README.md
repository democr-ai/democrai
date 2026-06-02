# Module Infrastructure

This package discovers, validates, loads and manages runtime modules. Modules
are application extensions loaded from `DEMOCRAI_MODULES_PATH`.

## Boundary

Modules use the SDK:

```python
from democrai.sdk import ...
```

Modules must not import core internals:

```python
from democrai.core import ...
```

The module loader checks Python imports and blocks core imports from modules.
Core may import module packages only inside controlled discovery/runtime flows.

## Runtime Paths

Modules are discovered from normalized runtime paths:

```bash
DEMOCRAI_MODULES_PATH
```

The `democrai` package is not used to infer where modules live.

## Key Files

- `manager.py`: module manager facade.
- `loading.py`: discovery, import boundary checks, manifest/RBAC/sidebar
  loading.
- `lifecycle.py`: trust, start/stop/reload and runtime registration.
- `runtime.py`: sandboxed module subject execution.
- `commands.py`: module lifecycle and scheduled commands.
- `command_state_store.py`: persisted command state.
- `compat.py`: platform, SDK/version compatibility and resource resolution.
- `registry.py`: internal runtime registry structures.

## Loading Flow

1. Discover module directories from runtime paths.
2. Validate compatibility and trust.
3. Enforce import boundaries.
4. Load manifest, RBAC, sidebar, locales and resources.
5. Register pages, actions, hooks and commands through SDK decorators.
6. Run startup hooks when the network loop is ready.

## Module Migrations

Module migrations belong to the module:

```text
modules/<module>/migrations/
```

Generate them with:

```bash
python main.py create-migration data --module <module> -m "description" --autogenerate
```

The runtime imports module models and includes only tables with this prefix:

```text
p_<module>_
```

The Alembic version table is module-specific:

```text
alembic_version_p_<module>
```

## Module UI

The current contract is YAML first:

- layout, components and bindings live in YAML.
- Python prepares minimal data and calls `builder.set_data(...)` or
  `builder.set_store(...)`.
- direct component mutation should be exceptional and documented.

## Rules

- Modules do not import core, clients or other internal layers.
- Modules do not choose database providers or sessions.
- Module resources are resolved from the module boundary.
- Actions use public SDK contracts.
- Missing public capabilities should be added to the SDK instead of bypassing
  the boundary.
