# Knowledge Graph Storage

This package persists knowledge graph nodes, relations and evidence. It is
consumed by the knowledge service, not directly by modules.

## Key Files

- `providers/base.py`: `KGStorageProvider`, `KGNode`, `KGEdge` and
  `KGEvidence` contracts.
- `providers/sqlite.py`: embedded SQLite provider on `kg.sqlite`.
- `providers/ladybug.py`: embedded LadybugDB provider on `kg.lbug`.
- `providers/neo4j.py`: remote Neo4j provider.
- `factory.py`: resolves provider from configuration/preferences.

## Boundary

Correct flow:

```text
module
  -> SDK knowledge/media API
  -> knowledge service
  -> KG storage
```

Modules must not import KG providers or write graph nodes and relations
directly. Public capabilities should be exposed through the SDK/knowledge
service.

## Scope

KG operations must preserve application scope:

- `user_id`
- `organization_id` when available

Providers and queries must keep scope for insert, query, update and delete
operations.

## Providers

Local:

- `sqlite`: default embedded provider for local development and desktop use.
- `ladybug`: embedded graph provider.

Remote:

- `neo4j`: remote graph provider for server deployments.

## Rules

- KG storage is not a public module API.
- Scope is part of the contract, not a caller-side convenience filter.
- Keep graph storage focused on persistence and query.
- Domain behavior belongs in the knowledge service.
