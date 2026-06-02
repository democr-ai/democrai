# Knowledge Graph Logical Contract

Il knowledge graph usa un contratto logico comune tra provider embedded
LadybugDB e provider remoto Neo4j.

## Entita'

`KGNode`:

- `id`: identificativo stabile applicativo.
- `type`: tipo logico del nodo.
- `user_id`: scope utente.
- `organization_id`: scope organizzazione opzionale.
- `properties`: proprieta' applicative arbitrarie.
- `name`, `external_ref`: campi indicizzabili/leggibili.
- `created_at`, `updated_at`, `deleted_at`: audit e soft delete.

`KGEdge`:

- `id`: identificativo stabile applicativo della relazione.
- `src`, `dst`: id applicativi dei nodi sorgente/destinazione nello stesso scope.
- `type`: tipo logico della relazione.
- `user_id`, `organization_id`: stesso scope dei nodi.
- `properties`: proprieta' applicative arbitrarie.
- `weight`, `confidence`, `evidence_id`, `source`: campi hot per retrieval e
  provenance.
- `created_at`, `updated_at`, `deleted_at`: audit e soft delete.

`KGEvidence`:

- `id`: identificativo stabile applicativo.
- `kind`, `ref`, `payload`: provenance del contenuto da cui deriva un edge.
- `user_id`, `organization_id`: scope.

## Regole Provider

- Il layer knowledge non deve usare Cypher o SQL direttamente.
- `type` resta un valore applicativo, non richiede table/label dinamiche.
- `properties` puo' essere serializzato dal provider, ma deve tornare come
  dizionario.
- `get_neighbors()` restituisce vicini 1-hop uscenti con metadati edge.
- `traversal()` restituisce `{"node_id": ..., "depth": ...}`.
- Le cancellazioni soft devono escludere nodi/edge da lookup, vicini e traversal.

## LadybugDB

Il provider embedded usa schema tecnico stabile:

- `KGNode`: node table unica.
- `Evidence`: node table unica.
- `KG_REL`: relationship table unica `FROM KGNode TO KGNode`.

LadybugDB richiede primary key su una sola colonna per node table, quindi il
provider usa una chiave scoped sintetica interna. Questa chiave non esce dal
contratto `KGStorageProvider`.

## Neo4j

Neo4j puo' mantenere label tecniche comuni `:KGNode` e relationship tecnica
`:KG_REL`. Eventuali label/type dinamici sono ottimizzazioni interne, non parte
del contratto applicativo.
