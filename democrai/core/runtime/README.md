# Runtime

`democrai.core.runtime` owns bootstrap, CLI handling, lifecycle, runtime paths,
dependency environments and application context. It is the entry boundary used
by launchers to start core.

## Runner Boundary

The local runner (`main.py`) is outside the core package. The runner:

- reads CLI arguments.
- sets runtime paths through environment variables when missing.
- decides whether desktop/web clients are started.
- may start server workers.
- calls `start_core_runtime(...)`.

Core receives normalized runtime options:

- `mode`: `desktop` or `server`.
- `http`, `host`, `port`, `workers`.
- module, engine and extractor paths.

Core must not assume that modules, engines, extractors or clients live next to
the installed package.

## Installed Launcher

The package also exposes:

```bash
democrai
```

The installed launcher is package-safe:

- starts core in server mode.
- handles CLI and migration commands.
- does not start development clients.
- does not rely on repository-local directories.

For repository-local development flows, `python main.py` remains valid.

## Entrypoint

Internal entrypoint:

```text
entrypoint.py
```

Responsibilities:

- build `CoreRuntimeOptions`.
- read `DEMOCRAI_MODULES_PATH`, `DEMOCRAI_ENGINES_PATH` and
  `DEMOCRAI_EXTRACTORS_PATH`.
- initialize runtime logging.
- start `RuntimeBootstrapper`.

## Bootstrap

The pipeline lives in:

```text
bootstrap/bootstrap_pipeline.py
bootstrap/bootstrap_pipeline_helpers.py
```

Conceptual order:

1. configuration and temporary paths.
2. sandbox/helper bootstrap when enabled.
3. storage.
4. engine/extractor registries.
5. network.
6. modules.
7. migrations.
8. background runtimes.
9. knowledge runtime.
10. HTTP/WebSocket according to mode.

The order is part of the internal contract because many phases depend on
`app_ctx`.

## CLI

The runtime CLI lives in `cli/` and handles:

- `migrate`
- `create-migration`
- `rollback`
- `migration-status`
- `validate-config`
- `reset-install`
- `module-status`
- `knowledge-rebuild`
- callable module commands

Migrations should go through the runner so paths, config and runtime metadata
are resolved as they are in the application.

## Foundation

`foundation/` contains:

- `app.py`: `app_ctx`, `req_ctx` and runtime contexts.
- `paths.py`: package base dir, data/cache/state/log dirs and extension paths.
- `registry.py`, `registry_types.py`: in-process registries.
- `di.py`: internal dependency injection helpers.

`get_base_dir()` points to the installed `democrai` package location, not
necessarily to modules, engines or extractors.

## Rules

- The runner decides clients; core decides runtime.
- Extension paths come from environment/options, not from `get_base_dir()`.
- Module migrations are generated on the `data --module` target.
- Core runtime does not import UI clients.
- Installable commands should be package entrypoints, not repository-local
  `main.py` dependencies.
