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
