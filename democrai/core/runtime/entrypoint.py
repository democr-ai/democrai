from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Iterable

from democrai.core.infrastructure.observability.logger.manager import LoggerManager
from democrai.core.runtime.bootstrap.bootstrap_pipeline import RuntimeBootstrapper
from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.runtime.foundation.paths import (
    ENGINES_PATH_ENV,
    EXTRACTORS_PATH_ENV,
    MODULES_PATH_ENV,
    logs_dir,
)


def _normalize_runtime_paths(paths: str | Iterable[str] | None) -> tuple[str, ...]:
    if paths is None:
        return ()
    if isinstance(paths, str):
        raw_items = paths.split(os.pathsep)
    else:
        raw_items = []
        for path in paths:
            raw_items.extend(str(path).split(os.pathsep))

    seen: set[str] = set()
    normalized: list[str] = []
    for item in raw_items:
        raw_path = str(item).strip()
        if not raw_path:
            continue
        real_path = os.path.realpath(os.path.abspath(os.path.expanduser(raw_path)))
        if real_path in seen:
            continue
        seen.add(real_path)
        normalized.append(real_path)
    return tuple(normalized)


@dataclass(frozen=True)
class CoreRuntimeOptions:
    mode: str = "desktop"
    http: bool = False
    host: str = "127.0.0.1"
    port: int = 8000
    workers: int = 1
    dev: int = 0
    listen_fd: int | None = None
    module_paths: tuple[str, ...] = field(default_factory=tuple)
    engine_paths: tuple[str, ...] = field(default_factory=tuple)
    extractor_paths: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_values(
        cls,
        *,
        mode: str = "desktop",
        http: bool = False,
        host: str = "127.0.0.1",
        port: int = 8000,
        workers: int = 1,
        dev: int = 0,
        listen_fd: int | None = None,
        modules_path: str | Iterable[str] | None = None,
        engines_path: str | Iterable[str] | None = None,
        extractors_path: str | Iterable[str] | None = None,
    ) -> "CoreRuntimeOptions":
        return cls(
            mode=mode,
            http=bool(http),
            host=str(host),
            port=int(port),
            workers=int(workers),
            dev=int(dev),
            listen_fd=listen_fd,
            module_paths=_normalize_runtime_paths(modules_path),
            engine_paths=_normalize_runtime_paths(engines_path),
            extractor_paths=_normalize_runtime_paths(extractors_path),
        )


def core_runtime_options_from_args(args) -> CoreRuntimeOptions:
    return CoreRuntimeOptions.from_values(
        mode=getattr(args, "mode", "desktop"),
        http=bool(getattr(args, "http", False)),
        host=getattr(args, "host", "127.0.0.1"),
        port=getattr(args, "port", 8000),
        workers=getattr(args, "workers", 1),
        dev=getattr(args, "dev", 0),
        listen_fd=getattr(args, "listen_fd", None),
        modules_path=os.environ.get(MODULES_PATH_ENV),
        engines_path=os.environ.get(ENGINES_PATH_ENV),
        extractors_path=os.environ.get(EXTRACTORS_PATH_ENV),
    )


def start_core_runtime(options: CoreRuntimeOptions) -> str | None:
    ctx = app_ctx()
    if options.dev:
        ctx.dev = True
    ctx.runtime_mode = options.mode
    ctx.runtime_module_paths = options.module_paths
    ctx.runtime_engine_paths = options.engine_paths
    ctx.runtime_extractor_paths = options.extractor_paths
    ctx.logger = LoggerManager(log_dir=str(logs_dir()))

    from democrai.core.application.ai.engine.manifests import list_engine_manifests
    from democrai.core.application.knowledge.extractor.manifests import list_extractor_manifests

    list_engine_manifests.cache_clear()
    list_extractor_manifests.cache_clear()

    return RuntimeBootstrapper().bootstrap(options)


__all__ = [
    "CoreRuntimeOptions",
    "ENGINES_PATH_ENV",
    "EXTRACTORS_PATH_ENV",
    "MODULES_PATH_ENV",
    "core_runtime_options_from_args",
    "start_core_runtime",
]
