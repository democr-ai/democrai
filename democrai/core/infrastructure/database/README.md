# Core Database

This package owns the internal runtime database (`democrai.db` locally). It is
not the application data database used by modules.

The core database stores identity, authorization, preferences, runtime
registries and shared technical state.

## Contains

- users, roles, permissions and organizations.
- global preferences.
- AI model registry and objective mappings.
- persisted engine/extractor registry state.
- minimal session state and technical metadata.
- access policy requests and approvals.
- persistent tasks and notifications.

## Does Not Contain

- module application data.
- module business tables.
- media payloads.
- vector embeddings.
- knowledge graph data.
- append-only observability events.

Those belong to their own storage domains.

## Key Files

- `models.py`: SQLAlchemy schema for the core database.
- `factory.py`: provider selection for `sqlite` and `postgres`.
- `providers/`: concrete database providers.
- `migrations/`: Alembic revisions for the core database.
- `migrations_handler.py`: migration runner.
- `preferences.py`: controlled preference access.
- `session_store.py`: session storage compatibility and composition.
- `access_policy.py`: access policy requests and approvals.

## Sessions

Session state is split conceptually into:

- identity: user and organization.
- UI state: navigation and explicit UI state.
- cache: transient technical values.

The legacy `sessions` table remains supported for compatibility. New runtime
code should prefer specialized storage and lazy migration paths.

## Providers

Local default:

```yaml
database:
  type: sqlite
```

Remote provider:

```yaml
database:
  type: postgres
  url: postgresql://user:pass@localhost/dbname
```

SQLite uses `get_data_dir()/democrai.db` and runtime WAL pragmas. Postgres uses
the same SQLAlchemy metadata and migration flow.

## Migrations

Use the runner:

```bash
python main.py create-migration db -m "description" --autogenerate
python main.py migrate db
python main.py rollback db --steps 1
python main.py migration-status db
```

Direct Alembic commands are only useful for local diagnosis. The normal flow
should go through the runner so paths, config and runtime metadata are resolved
the same way as the application.

## Boundary

This package is internal. Modules must not import `SessionLocal`, core models or
database helpers.

Module-facing access belongs in the SDK:

```python
from democrai.sdk import ...
```

If a value must be available to modules, expose it through the SDK or another
public contract.
