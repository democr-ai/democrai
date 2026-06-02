# Democr.ai

> Beta 0.0.1 - public preview. Not production-ready. APIs and behavior may change before the first stable release.

Democr.ai is a Python framework for building agentic AI applications with server-driven UI, observability, sandboxed extensibility, pluggable AI engines, and knowledge backends.

This PyPI package contains the core `democrai` Python package and SDK surface.

The full application repository also contains optional modules, engines, extractors, clients, benchmark scripts, documentation sources, and examples. Those repository assets are not part of this PyPI package.

## Links

- Website: https://democr.ai
- Documentation: https://democr.ai/docs/
- Repository: https://github.com/democr-ai/democrai

## Install

```bash
pip install democrai
```

Optional extras are available for common development/runtime needs:

```bash
pip install "democrai[desktop]"
pip install "democrai[dev]"
pip install "democrai[docs]"
pip install "democrai[hot-reload]"
```

## Scope

The package provides the framework runtime and public SDK.

Modules, engines, extractors, desktop/web clients, benchmark scripts, and deployment examples should be taken from the repository when needed.

## License

Democr.ai is distributed under AGPL-3.0-only and Apache-2.0 terms. See the repository for the full license files and third-party notices.
