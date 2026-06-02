# Getting Started

This page is the operational entrypoint for working on Democr.ai modules.

The application is a multi-runtime system:

- the **desktop client** talks to the backend through **IPC**
- the **web client** talks to the backend through **WebSocket**
- modules must stay behind the **SDK boundary**, regardless of transport

If you remember only one rule, remember this one: inside `modules/*`, `engines/*`, and `extractors/*`, import public APIs from `democrai.sdk.*`, not `democrai.core.*`.

## 1. Create the Environment

From the application root:

```bash
bash setup_venv.sh
source .venv/bin/activate
```

If you install dependencies manually, always keep constraints enabled:

```bash
source .venv/bin/activate
pip install -r requirements.txt -c constraints.txt
pip check
```

## 2. Understand Setup Mode

The runtime looks for `config.yaml` in the application data directory.

- if `config.yaml` is missing, the application starts in **setup mode**
- in setup mode, bootstrap uses minimal local providers
- once setup is completed and `config.yaml` exists, the full runtime boots normally

Useful config examples in the repository:

- `config.example.yaml`
- `config.distributed.example.yaml`

Validate a config file before using it:

```bash
source .venv/bin/activate
python main.py validate-config --path ./config.example.yaml
```

## 3. Run the Application

### Default launch

```bash
source .venv/bin/activate
python main.py
```

With no explicit `--mode`, the runtime starts in `desktop` mode.

### Desktop mode

```bash
python main.py --mode desktop
```

In desktop mode:

- the core runtime uses **IPC** as the primary transport
- the default client is `qtdesktop`
- the desktop client communicates with the backend through **IPC**
- if you do not pass `--http`, the embedded server is limited to the desktop/media-proxy flow

The default Qt client lives under `clients/qtdesktop`.

### Desktop mode with HTTP enabled

```bash
python main.py --mode desktop --http
```

This is still desktop mode, but it also exposes the HTTP/WebSocket server.

Use this when you need:

- the desktop application
- plus HTTP/WebSocket access for browser tools, hybrid flows, or external debugging

You can also combine desktop mode with a web client:

```bash
python main.py --mode desktop --http --client webclient
```

### Server mode

```bash
python main.py --mode server
```

In server mode:

- no client is started by default
- the backend exposes the WebSocket/HTTP transport
- browser clients talk to this runtime over **WebSocket**

To start a browser client from the runner:

```bash
python main.py --mode server --client webclient
```

The runner executes `yarn dev` in the selected client root:

- `clients/webclient`

If your shell is already inside a client directory, call the runner through the relative application path:

```bash
python ../../main.py --mode server --client webclient
```

Optional worker scaling:

```bash
python main.py --mode server --workers 4
```

### Dev mode

```bash
python main.py --mode desktop --dev 1
python main.py --mode server --dev 1
```

`--dev` enables development-oriented runtime behavior. Keep the value explicit because it is parsed as an integer flag.

### Runtime extension paths

The runner sets these environment variables when they are missing:

```bash
DEMOCRAI_MODULES_PATH
DEMOCRAI_ENGINES_PATH
DEMOCRAI_EXTRACTORS_PATH
```

By default they point to the application root directories:

- `modules`
- `engines`
- `extractors`

Override them before launching when you want the runtime to discover extensions from another location.

## 4. Run Migrations

Democr.ai manages more than one migration target.

Main commands:

```bash
python main.py migrate all
python main.py migration-status all
```

Targeted migrations are also supported:

```bash
python main.py migrate db
python main.py migrate data
python main.py migrate kg
python main.py migrate vector
python main.py migrate observability
```

Create a new migration:

```bash
python main.py create-migration db -m "add users index"
python main.py create-migration data -m "add module table" --autogenerate
python main.py create-migration data -m "add module table" --autogenerate --module tickets
```

When `--module <name>` is used with the `data` target, autogenerate imports the module models from the runtime module path and writes the migration inside that module, for example `modules/tickets/migrations/versions`.

Rollback:

```bash
python main.py rollback db --steps 1
python main.py rollback data --to <revision>
```

What these targets mean:

- `db`: main application database
- `data`: module-owned relational storage
- `kg`: knowledge storage
- `vector`: vector storage
- `observability`: observability storage

## 5. Check Runtime State

Useful CLI commands during development:

```bash
python main.py module-status --json
python main.py knowledge-rebuild --all --dry-run
python main.py reset-install
```

`reset-install` removes the active installation config and returns the app to setup mode.

## 6. SDK Boundary Rule

Inside `modules/*`, import from SDK domains only.

Good:

```python
from democrai.sdk.decorators import action
from democrai.sdk.auth import permission_required
from democrai.sdk.client import active_sdk as sdk
```

Bad:

```python
from democrai.core.application.routing.router import Router
from democrai.core.infrastructure.database.models import User
```

If a module, engine, or extractor capability is missing, extend the SDK first and then consume it from the extension code.

## 7. Choose the Right SDK Domain

Use the domain that matches the responsibility:

- `sdk.effects`: action return effects and incremental UI updates
- `sdk.models`: CRUD for core-managed entities
- `sdk.database`: persistence for module-owned tables
- `sdk.media`: uploads, downloads, persisted files, media references
- `sdk.ai`: tools, agents, pipelines, provider-backed AI calls
- `sdk.tasks`: background work and progress
- `sdk.i18n`: translations and language helpers

The module author should not care whether storage is local or distributed. That is exactly why media and persistence must go through the SDK.
