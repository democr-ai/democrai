# Runtime Configuration

Democr.ai runtime configuration is deployment configuration.

Modules, engines, and extractors should not read deployment details directly. They use the SDK boundary; the core runtime reads `config.yaml`, initializes providers, and exposes stable SDK domains.

## Where Configuration Lives

The runtime looks for `config.yaml` in the application data directory.

If the file is missing, the application starts in setup mode. Setup mode uses minimal local providers and lets the installation flow create the real configuration.

Useful repository examples:

```text
config.example.yaml
config.distributed.example.yaml
```

Validate a config before using it:

```bash
python main.py validate-config --path ./config.example.yaml
python main.py validate-config --path ./config.example.yaml --json
```

## Minimal Local Shape

A local-first setup keeps state on the machine running Democr.ai.

```yaml
database:
  type: sqlite
  data_type: sqlite

storage:
  media:
    type: local
    path: /home/user/.local/share/democrai/assets
  kg:
    type: sqlite
  vector:
    type: sqlite-vec
  observability:
    type: sqlite

network:
  redis:
    enabled: false

session:
  identity:
    provider: sqlite
  ui_state:
    provider: sqlite
  cache:
    provider: memory
```

This is the expected development and desktop shape.

## Distributed Shape

A distributed setup moves selected concerns to shared infrastructure.

```yaml
database:
  type: postgres
  url: postgresql://democrai:secret@localhost:5432/democrai_core
  data_type: postgres
  data_url: postgresql://democrai:secret@localhost:5432/democrai_data

storage:
  media:
    type: s3
    bucket: democrai-assets
    region: eu-west-1
  kg:
    type: neo4j
    uri: bolt://localhost:7687
    user: neo4j
    password: secret
  vector:
    type: milvus
    host: localhost
    port: 19530
  observability:
    type: postgres
    url: postgresql://democrai:secret@localhost:5432/democrai_observability

network:
  redis:
    enabled: true
    url: redis://localhost:6379/0

session:
  identity:
    provider: redis
  ui_state:
    provider: postgres
    url: postgresql://democrai:secret@localhost:5432/democrai_ui_state
  cache:
    provider: redis
```

Do not copy this as a production secret layout. It shows structure only.

## Runtime Services

The engine orchestrator and knowledge query service are configured as runtime services.

```yaml
ai:
  engine_orchestrator:
    enabled: true
    transport: tcp
    host: 127.0.0.1
    port: 40151
    startup_timeout_seconds: 30
    invoke_timeout_seconds: 0
    max_message_mb: 128
    scheduler_worker_count: 4
    invocation_worker_count: 4
    tls:
      enabled: false
      cert_file: ""
      key_file: ""
      ca_file: ""

knowledge:
  query_service:
    enabled: true
    host: 127.0.0.1
    port: 40153
    startup_timeout_seconds: 30
    timeout_seconds: 120
    max_message_mb: 64
    tls:
      enabled: false
      cert_file: ""
      key_file: ""
      ca_file: ""
```

On Linux and macOS the runtime can also use Unix sockets when configured for a service. On Windows, TCP is the normal transport.

For the engine orchestrator and knowledge query service, TCP exposed on
`0.0.0.0` or on a non-loopback host requires TLS. The runtime refuses to start
that configuration unless the matching service TLS flag is enabled:
`ai.engine_orchestrator.tls.enabled` or `knowledge.query_service.tls.enabled`.

TLS is server-side for now: each service presents `cert_file` and `key_file`,
clients verify it with `ca_file` when provided, and the internal service JWT
remains required on every RPC. Unix sockets and TCP loopback can run without
TLS. Mutual TLS is planned for a future multi-node hardening pass.

## Knowledge Configuration Split

Knowledge has two configuration layers.

YAML owns provider-level and runtime-level defaults:

```yaml
knowledge:
  vector_index:
    tenant_id: democrai
    app_id: knowledge
    name: items
    metric: cosine
  retrieval:
    graph_traversal_depth_default: 2
    graph_expansion_limit: 8
    graph_score_weight: 0.2
  runtime:
    poll_interval_seconds: 1.0
    batch_size: 16
    lease_seconds: 30
    max_attempts: 8
```

The system UI/database owns runtime choices such as:

- whether knowledge is enabled
- embedding model registry id
- rerank model registry id
- classification model registry id
- triple extractor model registry id
- MIME type to extractor bindings

Do not document new modules as if they should set embedding models or extractor bindings directly in `config.yaml`.

## Extension Discovery

Runtime extension roots can be configured with:

```yaml
modules:
  trust_mode: all
  allow_user_modules: true
  trusted_modules: []
  extra_paths:
    - /home/user/dev/democrai-modules

engines:
  extra_paths:
    - /home/user/dev/democrai-engines

extractors:
  extra_paths:
    - /home/user/dev/democrai-extractors
```
