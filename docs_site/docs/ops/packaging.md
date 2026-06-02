# Packaging Contract

The installable Python project is `democrai`.

The package should support:

```python
from democrai.sdk import ...
```

and should install the core runtime needed by package entrypoints.

## Included In The Wheel

The wheel includes Python packages matched by `democrai*`:

- `democrai.sdk`
- `democrai.core`
- `democrai.third_party`

`pyproject.toml` stays at repository root because that is the installable
project root.

## Not Included By Default

These repository folders are not part of the package by default:

- `modules`
- `engines`
- `extractors`
- `clients`

They are runtime inputs or independent applications.

Runtime extension roots are configured with:

```bash
DEMOCRAI_MODULES_PATH=/path/to/modules
DEMOCRAI_ENGINES_PATH=/path/to/engines
DEMOCRAI_EXTRACTORS_PATH=/path/to/extractors
```

## Installed Commands

The package exposes:

```bash
democrai
democrai-os-sandbox-helper
```

`democrai` is the package-safe core launcher. It starts the core server and
handles CLI commands. It does not start repository clients.

Examples:

```bash
democrai
democrai --host 127.0.0.1 --port 8000
democrai migrate all
democrai create-migration data --module system -m "message" --autogenerate
```

For local development with clients, use the repository runner:

```bash
python main.py --mode desktop --client qtdesktop
python main.py --mode server --client webclient
```

## Client Contract

Clients are independent applications:

- `clients/qtdesktop`
- `clients/webclient`

The repository runner can start them. The installed package launcher does not
bundle or start them.

## Built-in Extensions

If a future release needs built-in modules or engines, prefer one of these
explicit strategies:

- package them inside `democrai` as true built-ins with documented ownership.
- publish them as separate Python packages.
- keep them as runtime folders managed by deployment.

Do not rely on accidental repository-relative paths from inside the installed
package.
