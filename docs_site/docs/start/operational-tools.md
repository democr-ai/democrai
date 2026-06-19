# Operational Tools

This page lists the runtime commands that are useful while developing modules, providers, and local deployments.

Run commands from the application root with the virtual environment active.

```bash
source .venv/bin/activate
```

## Launch Modes

Desktop mode is the default.

```bash
python main.py
python main.py --mode desktop
```

Server mode exposes HTTP/WebSocket without starting a desktop client.

```bash
python main.py --mode server
```

Start a web client through the runner:

```bash
python main.py --mode server --client webclient
```

Expose HTTP/WebSocket while keeping desktop mode:

```bash
python main.py --mode desktop --http
```

## Config Validation

Validate provider keys and required dependencies before booting a config:

```bash
python main.py validate-config --path ./config.example.yaml
python main.py validate-config --path ./config.example.yaml --json
```

Use this before moving from local providers to Postgres, Redis, S3, Neo4j, Milvus, Pinecone, ClickHouse, or HTTP logging.

## Initial Setup

Run the first application setup from a YAML file:

```bash
python main.py setup path/to/setup.yaml
```

This is a core runtime command for setup-mode only. It starts the setup runtime, validates and saves the runtime configuration, finalizes setup through the core SDK, and creates the initial administrator account. It does not overwrite an existing application configuration.

Common options:

```bash
python main.py setup path/to/setup.yaml --json
python main.py setup path/to/setup.yaml --yes
```

YAML shape:

```yaml
admin:
  username: admin
  email: admin@example.com
  password: "${DEMOCRAI_ADMIN_PASSWORD}"

config:
  database:
    type: sqlite
  storage:
    media:
      type: local
      path: /path/to/media
```

The `config` section is the normal Democrai runtime configuration. Use `${NAME}` for administrator fields that should come from environment variables. If the admin password is omitted, the command asks for it interactively; non-interactive runs must provide it in YAML or through an environment variable.

## Migrations

Run all migration targets:

```bash
python main.py migrate all
python main.py migration-status all
```

Run one target:

```bash
python main.py migrate db
python main.py migrate data
python main.py migrate kg
python main.py migrate vector
python main.py migrate observability
```

Create migrations:

```bash
python main.py create-migration db -m "add index"
python main.py create-migration data -m "add module table" --autogenerate
python main.py create-migration data -m "add module table" --autogenerate --module chat
```

When `--module <name>` is used with the `data` target, autogenerate imports the module models and writes the migration under that module.

Rollback:

```bash
python main.py rollback db --steps 1
python main.py rollback data --to <revision>
```

## Module Runtime State

Show registered module commands and persisted command state:

```bash
python main.py module-status
python main.py module-status --json
python main.py module-status --module chat
```

This is useful when a module registers commands or background-capable entrypoints.

## Knowledge Rebuild

Queue rebuild jobs for knowledge sources:

```bash
python main.py knowledge-rebuild --all
python main.py knowledge-rebuild --all --dry-run
python main.py knowledge-rebuild --source-id <source-id>
```

Optional filters:

```bash
python main.py knowledge-rebuild --all --user-id 1
python main.py knowledge-rebuild --all --organization-id 1
python main.py knowledge-rebuild --all --source-type document
python main.py knowledge-rebuild --all --limit 100
python main.py knowledge-rebuild --all --json
```

Use `--dry-run` before queuing large rebuilds.

## Engine Installation

Install and activate engine instances from a YAML configuration file:

```bash
python main.py install-engines path/to/engines.yaml
```

This is a core runtime command. It starts the application runtime, uses the core SDK context, and follows the standard engine lifecycle: registry upsert, runtime config check, install, activation, optional model download, and model binding activation. It does not depend on an application module.

Common options:

```bash
python main.py install-engines path/to/engines.yaml --reset-mode keep
python main.py install-engines path/to/engines.yaml --reset-mode selected
python main.py install-engines path/to/engines.yaml --reset-mode full --yes
python main.py install-engines path/to/engines.yaml --json
```

Reset modes:

| Mode | Behavior |
|---|---|
| `keep` | Keep existing engines and models; update declared items and skip already available downloads |
| `selected` | Reset only engines and models declared in the YAML |
| `full` | Reset all engine registry rows, model bindings, and downloaded model artifacts; requires `--yes` outside interactive confirmation |

YAML shape:

```yaml
engines:
  - provider: <remote-provider-id>
    name: remote-main
    config:
      api_key: "${REMOTE_PROVIDER_API_KEY}"
    models:
      - id: <remote-model-id>
        activate: true

  - provider: <multi-instance-provider-id>
    instances:
      - name: multi-main
        config:
          api_key: "${MULTI_PROVIDER_API_KEY}"
        models:
          - id: <main-model-id>
            activate: true
      - name: multi-fast
        config:
          api_key: "${MULTI_PROVIDER_API_KEY}"
        models:
          - id: <fast-model-id>
            activate: true

  - provider: <local-provider-id>
    name: local-main
    models:
      - id: <downloadable-model-id>
        download: true
        activate: true
```

Use `${NAME}` for sensitive configuration values that should come from environment variables. Provider ids, model ids, and configuration fields come from the engine manifests available in the running Democrai application. When multiple instances use the same provider, provider installation runs once and each instance is activated separately. Any concrete YAML shipped with an application or repository should be treated as an implementation example, not as the framework contract.

## Extractor Installation

Install and activate knowledge extractors from a YAML configuration file:

```bash
python main.py install-extractors path/to/extractors.yaml
```

This is a core runtime command. It starts the application runtime, uses the core SDK context, installs extractor dependencies, marks extractors active, synchronizes the extractor runtime, and applies declared MIME bindings. Extractor ids, runtime configuration, and supported MIME types come from the extractor manifests available in the running Democrai application.

Common options:

```bash
python main.py install-extractors path/to/extractors.yaml --reset-mode keep
python main.py install-extractors path/to/extractors.yaml --reset-mode selected
python main.py install-extractors path/to/extractors.yaml --reset-mode full --yes
python main.py install-extractors path/to/extractors.yaml --json
```

YAML shape:

```yaml
extractors:
  - id: <document-extractor-id>
    install_config:
      option_name: option_value
    runtime_config:
      chunk_size: 1200
    mime_bindings:
      - application/pdf
      - text/plain

  - id: <ai-extractor-id>
    runtime_config:
      model_registry_id: 12
    mime_bindings:
      - <supported-mime-type>
```

AI-backed extractors that require a model must reference a real `model_registry_id` for an already configured model with the required capability. If that field is omitted for an extractor that needs it, the command can still install and activate the extractor, but its runtime configuration is incomplete and extraction will not be usable until that field is saved. Concrete extractor YAML files shipped with an application or repository are implementation examples, not required framework components.

## Reset Installation

Return the application to setup mode:

```bash
python main.py reset-install
```

Optionally include local filesystem media in the reset flow:

```bash
python main.py reset-install --include-media
```

This command is for local development and installation recovery. Treat it as destructive operational tooling.

## Module Commands

If the first positional argument is not a known runtime command, the launcher treats it as a module callable command.

That path is for module-defined commands, not for normal UI actions.
