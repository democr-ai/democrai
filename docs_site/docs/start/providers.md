# Providers

Providers decide which implementation owns each runtime concern.

The module author should not care whether persistence is local SQLite, Postgres, Redis, S3, Milvus, or Neo4j. Modules use SDK domains; provider selection happens in runtime configuration and system-managed registries.

Provider implementations may exist before they are certified through the current
integration pass. Treat provider lists as implementation inventory unless a
component is explicitly listed as tested in release notes or the README.

## Provider Map

| Concern | Config key | Supported values |
| --- | --- | --- |
| Core database | `database.type` | `sqlite`, `postgres` |
| Application data database | `database.data_type` | `sqlite`, `postgres`, `supabase` |
| Media storage | `storage.media.type` | `local`, `s3` |
| Knowledge graph storage | `storage.kg.type` | `sqlite`, `ladybug`, `neo4j` |
| Vector storage | `storage.vector.type` | `sqlite-vec`, `milvus`, `pinecone` |
| Observability storage | `storage.observability.type` | `sqlite`, `postgres`, `clickhouse` |
| Session identity | `session.identity.provider` | `sqlite`, `redis` |
| UI state | `session.ui_state.provider` | `sqlite`, `postgres`, `redis` |
| Session cache | `session.cache.provider` | `memory`, `redis` |
| WebSocket codec | `network.ws.codec` | `json`, `deflate-json` |
| Logging | `logging.provider` | `local`, `http` |
| Module trust | `modules.trust_mode` | `all`, `trusted_only` |

These values come from runtime config validation. If you add a provider, update validation and documentation together.

Current implementations that still require certification include Pinecone and
ClickHouse. They should not be presented as tested components until validated
through real application flows.

## Required Keys By Provider

Some provider choices require additional keys.

| Selection | Required keys |
| --- | --- |
| `database.type: postgres` | `database.url` |
| `database.data_type: postgres` | `database.data_url` |
| `database.data_type: supabase` | `database.data_url` |
| `storage.media.type: s3` | `storage.media.bucket` |
| `storage.kg.type: neo4j` | `storage.kg.uri`, `storage.kg.user`, `storage.kg.password` |
| `storage.vector.type: milvus` | `storage.vector.host` |
| `storage.vector.type: pinecone` | `storage.vector.api_key` or `PINECONE_API_KEY` |
| `storage.observability.type: postgres` | `storage.observability.url` |
| `storage.observability.type: clickhouse` | `storage.observability.url` |
| `session.ui_state.provider: postgres` | `session.ui_state.url` |
| any Redis session provider | `session.redis.url` or `network.redis.url` |
| `network.redis.enabled: true` | `network.redis.url` |
| `logging.provider: http` | `logging.url` |

## Media Provider

Modules should use `sdk.media`.

They should not build runtime-facing media URLs manually. The active media provider may be local or object-backed, and the SDK is responsible for producing safe references and public URLs.

## Database Providers

There are two database concerns:

- core database: users, roles, auth, installation state, and core-managed tables
- data database: module-owned data and application data

Module-owned models use module data storage through the SDK/database boundary. Core-managed entities use `sdk.models`.

## Knowledge Providers

Knowledge combines several providers:

- extractor registry and MIME bindings
- embedding model selected from model registry
- vector provider
- graph provider
- query service
- ingestion runtime

Extractor and model selection are runtime state, not hardcoded module behavior. Modules ask `sdk.knowledge` and `sdk.extractors` for active capabilities.

## Engine Providers

Engines are installable runtime providers for model methods such as:

- `generate_completion`
- `generate_stream`
- embeddings
- speech-to-text
- text-to-speech
- image analysis

The system module installs and configures engines and model registry rows. Feature code should resolve providers through `sdk.ai`, not import engine implementation classes.

## Extractor Providers

Extractors are installable runtimes that convert files into structured extraction payloads.

The normal flow is:

1. upload or reference media through SDK/media
2. resolve extractor through configured MIME bindings
3. enqueue extraction
4. let background workers produce full markdown and chunks
5. optionally ingest chunks into knowledge

Modules should not decide supported MIME types from a hardcoded local list. Use SDK extractor helpers.
