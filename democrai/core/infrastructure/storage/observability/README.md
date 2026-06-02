# Observability Storage

This package persists technical runtime events and audits. It records what
happened; it does not decide application behavior.

## Contains

- runtime events.
- application audits.
- AI/model runtime calls.
- tool, agent and pipeline events.
- task and operational metrics when routed through the service layer.
- errors and correlation ids useful for diagnosis.

## Does Not Contain

- primary application state.
- module business data.
- policy decisions.
- high-frequency progress that can remain transient.

Frequent progress should use streams/runtime events and persist only meaningful
phase changes or final state.

## Key Files

- `models.py`: event envelope and local tables.
- `store.py`: read/write facade.
- `providers/`: `sqlite`, `postgres` and `clickhouse` backends.
- `exporters/`: optional side effects such as OTLP.
- `factory.py`: composes store, provider and exporters from configuration.
- `migrations/`: SQLAlchemy schema for relational backends.

## Event Envelope

Events should be append-only records with:

- timestamp.
- severity/level.
- category.
- event name.
- user/organization scope when available.
- correlation id.
- optional duration.
- serializable JSON payload.

Payloads must support diagnosis without becoming the primary database for a
feature.

## Backends

Local default:

```yaml
storage:
  observability:
    type: sqlite
```

Relational backend:

```yaml
storage:
  observability:
    type: postgres
    url: postgresql://user:pass@localhost/democrai_obs
```

Analytics backend:

```yaml
storage:
  observability:
    type: clickhouse
    url: clickhouse://localhost:9000/democrai
```

`sqlite` and `postgres` use Alembic migrations. `clickhouse` uses dedicated
schema bootstrap.

## Rules

- Do not use observability as application source of truth.
- Do not persist noisy progress if it can stay in runtime streams.
- Exporters must not change application outcomes.
- Keep payloads small, serializable and free of secrets.
