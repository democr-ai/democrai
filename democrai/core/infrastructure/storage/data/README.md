# Data Storage

This package owns the application data database (`data.db` locally). It is
separate from the core database: module data, application data and module-owned
tables live here.

Core owns runtime orchestration. Modules must access this storage only through
the SDK.

## Boundary

Internal core usage:

- SQLAlchemy providers, sessions and connections.
- data-domain migrations.
- module model loading for migration autogenerate.
- automatic authorization filters.

Module usage:

```python
from democrai.sdk.database import ...
```

Modules must not import:

```python
from democrai.core.infrastructure.storage.data import ...
```

## Key Files

- `database.py`: engine and session initialization for the data database.
- `factory.py`: resolves `database.data_type`.
- `store.py`: scoped CRUD behavior and authorization filters.
- `module_base.py`: base model support for module tables.
- `migrations_handler.py`: applies core data migrations and module migrations.
- `models.py`: data-domain core tables when needed.

## Module Tables

Module tables use a module prefix:

```text
p_<module>_<table>
```

This keeps autogenerate and migration ownership isolated. A module migration
must not capture core tables or tables owned by another module.

## Authorization Scope

The data store applies user and organization filters for scoped module models.
Module code should express queries through SDK/model contracts and should not
manually reproduce scope filters.

## Migrations

Core data migrations:

```bash
python main.py create-migration data -m "description" --autogenerate
python main.py migrate data
```

Module migrations:

```bash
python main.py create-migration data --module <module> -m "description" --autogenerate
python main.py migrate data --module <module>
```

## Rules

- Module migrations live in the module.
- Modules import database contracts from the SDK.
- Core may import module models only during controlled discovery/migration
  flows.
- Modules must not access core sessions, engines or providers directly.
