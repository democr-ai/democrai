from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from typing import Callable, Optional

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine
from sqlalchemy import MetaData

from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.runtime.foundation.paths import (
    get_base_dir,
    get_data_dir,
    get_runtime_module_dirs,
    logs_dir,
)
from democrai.core.platform.config.yaml_config import YamlConfigProvider
from democrai.core.infrastructure.observability.logger.manager import LoggerManager


MetadataFactory = Callable[[], object]
UrlFactory = Callable[[], str]


_MODULE_DATA_ENV = """from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

config = context.config
injected_include_object = config.attributes.get("include_object")
target_metadata = config.attributes.get("target_metadata")
DATABASE_URL = config.attributes.get("db_url")

if target_metadata is None or not DATABASE_URL:
    raise RuntimeError(
        "Module migrations must be run through Democr.ai migration commands."
    )

config.set_main_option("sqlalchemy.url", DATABASE_URL)

version_table_configured = config.get_main_option("version_table")
if not version_table_configured:
    config.set_main_option("version_table", "alembic_version_data")


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    version_table = config.get_main_option("version_table", "alembic_version_data")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        include_object=injected_include_object,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
        version_table=version_table,
        transactional_ddl=True,
        transaction_per_migration=False,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    version_table = config.get_main_option("version_table", "alembic_version_data")
    with connectable.connect() as connection:
        with connection.begin():
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                include_object=injected_include_object,
                render_as_batch=True,
                version_table=version_table,
                transactional_ddl=True,
                transaction_per_migration=False,
            )

            with context.begin_transaction():
                context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
"""


@dataclass(frozen=True)
class MigrationTarget:
    name: str
    label: str
    ini_path: str
    script_location: str
    metadata_factory: MetadataFactory
    url_factory: UrlFactory
    version_table: Optional[str] = None


@dataclass(frozen=True)
class MigrationStatus:
    target: str
    label: str
    current_revision: str | None
    head_revision: str | None
    up_to_date: bool


def _init_cli_context() -> None:
    ctx = app_ctx()
    if ctx.logger is None:
        ctx.logger = LoggerManager(log_dir=str(logs_dir()))
    if ctx.config is None:
        ctx.config = YamlConfigProvider(os.path.join(get_data_dir(), "config.yaml"))


def _db_metadata():
    from democrai.core.infrastructure.database.models import Base

    return Base.metadata


def _db_url() -> str:
    from democrai.core.infrastructure.database import get_database_url

    return get_database_url()


def _load_module_models() -> None:
    """Import all module models so their tables are registered in Base.metadata."""
    for module_name in _iter_runtime_module_names():
        try:
            _import_module_models(module_name)
        except ImportError:
            pass


def _core_data_metadata():
    from democrai.core.infrastructure.storage.data.models import Base

    return Base.metadata


def _data_metadata():
    _load_module_models()
    return _core_data_metadata()


def _data_url() -> str:
    from democrai.core.infrastructure.storage.data.database import get_database_url

    return get_database_url()


def _observability_metadata():
    from democrai.core.infrastructure.storage.observability.models import Base

    return Base.metadata


def _observability_url() -> str:
    provider = app_ctx().config or YamlConfigProvider(
        os.path.join(get_data_dir(), "config.yaml")
    )
    obs_type = str(provider.get("storage.observability.type", "sqlite")).strip().lower()
    obs_url = provider.get("storage.observability.url")
    if obs_type == "sqlite" or not obs_url:
        return f"sqlite:///{os.path.join(get_data_dir(), 'observability.db')}"
    return obs_url


def _vector_metadata():
    from democrai.core.infrastructure.storage.vector.models import Base

    return Base.metadata


def _vector_url() -> str:
    return f"sqlite:///{os.path.join(get_data_dir(), 'vector.db')}"


def _target_specs() -> dict[str, MigrationTarget]:
    base_dir = get_base_dir()
    return {
        "db": MigrationTarget(
            name="db",
            label="DB",
            ini_path=os.path.join(
                base_dir, "core", "infrastructure", "database", "alembic.ini"
            ),
            script_location=os.path.join(
                base_dir, "core", "infrastructure", "database", "migrations"
            ),
            metadata_factory=_db_metadata,
            url_factory=_db_url,
        ),
        "data": MigrationTarget(
            name="data",
            label="DATA DB",
            ini_path=os.path.join(
                base_dir,
                "core",
                "infrastructure",
                "storage",
                "data",
                "alembic.ini",
            ),
            script_location=os.path.join(
                base_dir,
                "core",
                "infrastructure",
                "storage",
                "data",
                "migrations",
            ),
            metadata_factory=_data_metadata,
            url_factory=_data_url,
            version_table="alembic_version_data",
        ),
        "observability": MigrationTarget(
            name="observability",
            label="OBS DB",
            ini_path=os.path.join(
                base_dir,
                "core",
                "infrastructure",
                "storage",
                "observability",
                "alembic.ini",
            ),
            script_location=os.path.join(
                base_dir,
                "core",
                "infrastructure",
                "storage",
                "observability",
                "migrations",
            ),
            metadata_factory=_observability_metadata,
            url_factory=_observability_url,
        ),
        "vector": MigrationTarget(
            name="vector",
            label="VECTOR DB",
            ini_path=os.path.join(
                base_dir,
                "core",
                "infrastructure",
                "storage",
                "vector",
                "alembic.ini",
            ),
            script_location=os.path.join(
                base_dir,
                "core",
                "infrastructure",
                "storage",
                "vector",
                "migrations",
            ),
            metadata_factory=_vector_metadata,
            url_factory=_vector_url,
        ),
    }


ALL_TARGETS = ("db", "vector", "data", "observability")
CREATE_TARGETS = ("db", "data", "observability", "vector")
ROLLBACK_TARGETS = CREATE_TARGETS


def _is_clickhouse_observability_target(target: MigrationTarget) -> bool:
    if target.name != "observability":
        return False
    provider = app_ctx().config or YamlConfigProvider(
        os.path.join(get_data_dir(), "config.yaml")
    )
    obs_type = str(provider.get("storage.observability.type", "sqlite")).strip().lower()
    return obs_type == "clickhouse"


def _build_config(target: MigrationTarget) -> Config:
    cfg = Config(target.ini_path)
    cfg.set_main_option("script_location", target.script_location)
    db_url = target.url_factory()
    cfg.set_main_option("sqlalchemy.url", db_url)
    cfg.attributes["target_metadata"] = target.metadata_factory()
    cfg.attributes["db_url"] = db_url
    if target.version_table:
        cfg.set_main_option("version_table", target.version_table)
    return cfg


def _data_alembic_ini_path() -> str:
    return os.path.join(
        get_base_dir(),
        "core",
        "infrastructure",
        "storage",
        "data",
        "alembic.ini",
    )


def _data_core_migrations_dir() -> str:
    return os.path.join(
        get_base_dir(),
        "core",
        "infrastructure",
        "storage",
        "data",
        "migrations",
    )


def _module_dir(module_name: str) -> str:
    for modules_dir in get_runtime_module_dirs():
        candidate = os.path.join(modules_dir, module_name)
        if os.path.isdir(candidate):
            return candidate
    return ""


def _iter_runtime_module_names() -> tuple[str, ...]:
    names: list[str] = []
    seen: set[str] = set()
    for modules_dir in get_runtime_module_dirs():
        if not os.path.isdir(modules_dir):
            continue
        for entry in os.scandir(modules_dir):
            if not entry.is_dir():
                continue
            module_name = str(entry.name or "").strip()
            if not module_name or module_name in seen:
                continue
            seen.add(module_name)
            names.append(module_name)
    return tuple(names)


def _module_model_import_candidates(module_name: str) -> tuple[str, ...]:
    module_dir = _module_dir(module_name)
    if not module_dir:
        return ()
    modules_dir = os.path.dirname(module_dir)
    root_package = os.path.basename(modules_dir)
    candidates: list[str] = []
    if root_package:
        candidates.append(f"{root_package}.{module_name}.models")
    candidates.append(f"{module_name}.models")
    deduped: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        deduped.append(candidate)
    return tuple(deduped)


def _install_module_model_import_paths(module_name: str) -> None:
    module_dir = _module_dir(module_name)
    if not module_dir:
        raise ValueError(f"Unknown module: {module_name}")
    modules_dir = os.path.dirname(module_dir)
    modules_parent = os.path.dirname(modules_dir)
    for candidate in (modules_dir, modules_parent):
        if candidate and candidate not in sys.path:
            sys.path.insert(0, candidate)


def _import_module_models(module_name: str):
    import importlib

    from democrai.sdk.database import module_database_context

    _install_module_model_import_paths(module_name)
    candidates = _module_model_import_candidates(module_name)
    if not candidates:
        raise ValueError(f"Unknown module: {module_name}")
    last_error: ImportError | None = None
    with module_database_context(module_name):
        for candidate in candidates:
            try:
                return importlib.import_module(candidate)
            except ModuleNotFoundError as exc:
                missing_name = str(getattr(exc, "name", "") or "").strip()
                if missing_name in {candidate, candidate.rsplit(".", 1)[0], candidate.split(".", 1)[0]}:
                    last_error = exc
                    continue
                raise
        if last_error is not None:
            raise last_error
    return None


def _module_migrations_dir(module_name: str) -> str:
    module_dir = _module_dir(module_name)
    if not module_dir:
        raise ValueError(f"Unknown module: {module_name}")
    return os.path.join(module_dir, "migrations")


def _ensure_data_module_migration_scaffold(module_name: str) -> str:
    module_dir = _module_dir(module_name)
    if not os.path.isdir(module_dir):
        raise ValueError(f"Unknown module: {module_name}")

    script_location = _module_migrations_dir(module_name)
    os.makedirs(script_location, exist_ok=True)
    os.makedirs(os.path.join(script_location, "versions"), exist_ok=True)

    core_script_location = _data_core_migrations_dir()
    for filename in ("env.py", "script.py.mako"):
        destination = os.path.join(script_location, filename)
        if not os.path.exists(destination):
            if filename == "env.py":
                with open(destination, "w", encoding="utf-8") as handle:
                    handle.write(_MODULE_DATA_ENV)
            else:
                source = os.path.join(core_script_location, filename)
                shutil.copyfile(source, destination)
    return script_location


def _object_table_name(object_, compare_to) -> str:
    for candidate in (object_, compare_to):
        if candidate is None:
            continue
        table = getattr(candidate, "table", None)
        if table is not None:
            name = getattr(table, "name", "")
            if name:
                return str(name)
        name = getattr(candidate, "name", "")
        if isinstance(name, str) and name:
            return name
    return ""


def _build_scope_include_object(*, table_predicate: Callable[[str], bool]):
    def include_object(object_, name, type_, reflected, compare_to):
        if type_ == "table":
            table_name = str(name or "")
        else:
            table_name = _object_table_name(object_, compare_to)
        if not table_name:
            return True
        return table_predicate(table_name)

    return include_object


def _core_data_include_object():
    return _build_scope_include_object(
        table_predicate=lambda table_name: not str(table_name).startswith("p_")
    )


def _module_data_include_object(module_name: str):
    prefix = f"p_{module_name}_"
    return _build_scope_include_object(
        table_predicate=lambda table_name: str(table_name).startswith(prefix)
    )


def _module_data_metadata(module_name: str) -> MetaData:
    from democrai.core.infrastructure.storage.data.mixins import Base

    _import_module_models(module_name)

    metadata = MetaData()
    prefix = f"p_{module_name}_"
    for table in Base.metadata.sorted_tables:
        if str(table.name).startswith(prefix):
            table.to_metadata(metadata)
    return metadata


def _build_data_scope_config(
    *,
    script_location: str,
    metadata_factory: Callable[[], object],
    version_table: str,
    include_object=None,
) -> Config:
    cfg = Config(_data_alembic_ini_path())
    cfg.set_main_option("script_location", script_location)
    db_url = _data_url()
    cfg.set_main_option("sqlalchemy.url", db_url)
    cfg.set_main_option("version_table", version_table)
    cfg.attributes["target_metadata"] = metadata_factory()
    cfg.attributes["db_url"] = db_url
    if include_object is not None:
        cfg.attributes["include_object"] = include_object
    return cfg


def _suppress_empty_revision(context, revision, directives) -> None:
    if not directives:
        return
    script = directives[0]
    if (
        getattr(script, "upgrade_ops", None) is not None
        and script.upgrade_ops.is_empty()
    ):
        directives[:] = []


def _create_data_scope_revision(
    *,
    scope_label: str,
    message: str,
    autogenerate: bool,
    script_location: str,
    metadata_factory: Callable[[], object],
    version_table: str,
    include_object=None,
) -> bool:
    cfg = _build_data_scope_config(
        script_location=script_location,
        metadata_factory=metadata_factory,
        version_table=version_table,
        include_object=include_object,
    )
    revision_result = command.revision(
        cfg,
        message=message,
        autogenerate=autogenerate,
        process_revision_directives=_suppress_empty_revision if autogenerate else None,
    )
    created = bool(revision_result)
    if created:
        print(f"[DATA DB] created revision for {scope_label}")
    elif autogenerate:
        print(f"[DATA DB] no schema changes for {scope_label}")
    return created


def _create_data_migration(
    message: str,
    *,
    autogenerate: bool,
    module_name: str | None = None,
) -> int:
    if module_name:
        script_location = _ensure_data_module_migration_scaffold(module_name)
        print(
            f"[DATA DB] creating revision for module {module_name}: {message}"
            + (" (autogenerate)" if autogenerate else "")
        )
        _create_data_scope_revision(
            scope_label=f"module {module_name}",
            message=message,
            autogenerate=autogenerate,
            script_location=script_location,
            metadata_factory=lambda: _module_data_metadata(module_name),
            version_table=f"alembic_version_p_{module_name}",
            include_object=_module_data_include_object(module_name),
        )
        return 0

    if not autogenerate:
        target = _target_specs()["data"]
        cfg = _build_config(target)
        print(f"[{target.label}] creating revision: {message}")
        command.revision(cfg, message=message, autogenerate=False)
        return 0

    print(f"[DATA DB] creating revision: {message} (autogenerate)")
    _create_data_scope_revision(
        scope_label="core",
        message=message,
        autogenerate=True,
        script_location=_data_core_migrations_dir(),
        metadata_factory=_core_data_metadata,
        version_table="alembic_version_data",
        include_object=_core_data_include_object(),
    )

    for module_name in _iter_runtime_module_names():
        try:
            metadata = _module_data_metadata(module_name)
        except ImportError:
            continue
        if not metadata.tables:
            continue
        _ensure_data_module_migration_scaffold(module_name)
        _create_data_scope_revision(
            scope_label=f"module {module_name}",
            message=message,
            autogenerate=True,
            script_location=_module_migrations_dir(module_name),
            metadata_factory=lambda name=module_name: _module_data_metadata(name),
            version_table=f"alembic_version_p_{module_name}",
            include_object=_module_data_include_object(module_name),
        )
    return 0


def _resolve_targets(target_name: str) -> list[MigrationTarget]:
    specs = _target_specs()
    if target_name == "all":
        return [specs[name] for name in ALL_TARGETS]
    return [specs[target_name]]


def migrate(target_name: str) -> int:
    _init_cli_context()
    if target_name == "data":
        from democrai.core.infrastructure.storage.data.migrations_handler import (
            run_data_migrations,
        )

        print("[DATA DB] upgrading core and module migrations to head")
        run_data_migrations()
        return 0
    for target in _resolve_targets(target_name):
        if _is_clickhouse_observability_target(target):
            from democrai.core.infrastructure.storage.observability.providers.clickhouse import (
                ClickHouseObsStorage,
            )

            print(f"[{target.label}] bootstrapping clickhouse schema")
            ClickHouseObsStorage(target.url_factory()).run_migrations()
            continue
        cfg = _build_config(target)
        print(f"[{target.label}] upgrading to head")
        command.upgrade(cfg, "head")
    return 0


def create_migration(
    target_name: str,
    message: str,
    *,
    autogenerate: bool = False,
    module_name: str | None = None,
) -> int:
    _init_cli_context()
    if module_name and target_name != "data":
        raise ValueError("--module is supported only for the data target")
    if target_name == "data":
        return _create_data_migration(
            message,
            autogenerate=autogenerate,
            module_name=module_name,
        )
    target = _resolve_targets(target_name)[0]
    if _is_clickhouse_observability_target(target):
        raise ValueError("clickhouse observability uses managed schema bootstrap only")
    cfg = _build_config(target)
    print(
        f"[{target.label}] creating revision: {message}"
        + (" (autogenerate)" if autogenerate else "")
    )
    command.revision(cfg, message=message, autogenerate=autogenerate)
    return 0


def rollback(
    target_name: str, *, steps: int | None = None, revision: str | None = None
) -> int:
    _init_cli_context()
    target = _resolve_targets(target_name)[0]
    if _is_clickhouse_observability_target(target):
        raise ValueError("clickhouse observability does not support alembic rollback")
    cfg = _build_config(target)
    if revision is not None:
        destination = revision
    elif steps is not None:
        destination = f"-{steps}"
    else:
        raise ValueError("rollback requires either steps or revision")

    print(f"[{target.label}] downgrading to {destination}")
    command.downgrade(cfg, destination)
    return 0


def _get_status(target: MigrationTarget) -> MigrationStatus:
    if _is_clickhouse_observability_target(target):
        return MigrationStatus(
            target=target.name,
            label=target.label,
            current_revision="clickhouse-managed",
            head_revision="clickhouse-managed",
            up_to_date=True,
        )
    cfg = _build_config(target)
    script = ScriptDirectory.from_config(cfg)
    head_revision = script.get_current_head()

    engine = create_engine(target.url_factory())
    try:
        with engine.connect() as connection:
            context = MigrationContext.configure(
                connection,
                opts={"version_table": target.version_table or "alembic_version"},
            )
            current_revision = context.get_current_revision()
    finally:
        engine.dispose()

    return MigrationStatus(
        target=target.name,
        label=target.label,
        current_revision=current_revision,
        head_revision=head_revision,
        up_to_date=current_revision == head_revision,
    )


def migration_status(target_name: str) -> int:
    _init_cli_context()
    for target in _resolve_targets(target_name):
        status = _get_status(target)
        current = status.current_revision or "<none>"
        head = status.head_revision or "<none>"
        state = "ok" if status.up_to_date else "pending"
        print(f"[{status.label}] current={current} head={head} status={state}")
    return 0
