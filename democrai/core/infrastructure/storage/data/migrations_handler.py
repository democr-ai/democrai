import json
import os
import sys
from alembic.config import Config
from alembic import command
from alembic.autogenerate import rewriter
from alembic.operations import ops
from sqlalchemy import MetaData
from democrai.core.application.auth.service import validate_module_name
from democrai.core.runtime.foundation.paths import get_base_dir, get_data_dir
from democrai.core.runtime.foundation.paths import get_runtime_module_dirs
from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.infrastructure.storage.errors import MigrationError
from democrai.core.platform.utils.normalize import normalize_bool
from democrai.sdk.database import module_database_context


def get_current_db_url() -> str:
    """Helper to get the current database URL from app_ctx or config."""
    ctx = app_ctx()
    if (
        ctx
        and hasattr(ctx, "data_store")
        and ctx.data_store
        and hasattr(ctx.data_store, "url")
    ):
        return ctx.data_store.url

    from democrai.core.infrastructure.storage.data.database import get_database_url

    return get_database_url()


def get_migration_rewriter(prefix: str) -> rewriter.Rewriter:
    """
    Returns an Alembic Rewriter that automatically prefixes table and index names.
    """
    writer = rewriter.Rewriter()

    @writer.rewrites(ops.CreateTableOp)
    def prefix_create_table(context, revision, op):
        op.table_name = f"{prefix}{op.table_name}"
        return op

    @writer.rewrites(ops.DropTableOp)
    def prefix_drop_table(context, revision, op):
        op.table_name = f"{prefix}{op.table_name}"
        return op

    @writer.rewrites(ops.CreateIndexOp)
    def prefix_create_index(context, revision, op):
        op.table_name = f"{prefix}{op.table_name}"
        if not op.index_name.startswith(prefix):
            op.index_name = f"{prefix}{op.index_name}"
        return op

    @writer.rewrites(ops.DropIndexOp)
    def prefix_drop_index(context, revision, op):
        op.table_name = f"{prefix}{op.table_name}"
        if not op.index_name.startswith(prefix):
            op.index_name = f"{prefix}{op.index_name}"
        return op

    @writer.rewrites(ops.AddColumnOp)
    def prefix_add_column(context, revision, op):
        op.table_name = f"{prefix}{op.table_name}"
        return op

    @writer.rewrites(ops.DropColumnOp)
    def prefix_drop_column(context, revision, op):
        op.table_name = f"{prefix}{op.table_name}"
        return op

    @writer.rewrites(ops.AlterColumnOp)
    def prefix_alter_column(context, revision, op):
        op.table_name = f"{prefix}{op.table_name}"
        return op

    @writer.rewrites(ops.AlterTableOp)
    def prefix_alter_table(context, revision, op):
        op.table_name = f"{prefix}{op.table_name}"
        return op

    @writer.rewrites(ops.CreateForeignKeyOp)
    def prefix_create_fk(context, revision, op):
        op.source_table = f"{prefix}{op.source_table}"
        # We assume referent_table is also within the same module for now
        # unless it already starts with a known core or other module prefix.
        if not op.referent_table.startswith("p_") and not op.referent_table.startswith(
            "core_"
        ):
            op.referent_table = f"{prefix}{op.referent_table}"
        return op

    return writer


def run_data_migrations() -> None:
    """
    Runs migrations for the main data database (core and modules).
    """
    base_dir = get_base_dir()
    _ = get_data_dir()

    # 1. Run CORE migrations
    alembic_cfg_path = os.path.join(
        base_dir, "core", "infrastructure", "storage", "data", "alembic.ini"
    )
    app_ctx().logger.info(
        f"[DATA DB] Running CORE migrations from {alembic_cfg_path}..."
    )

    core_cfg = Config(alembic_cfg_path)
    core_migrations_dir = os.path.join(
        base_dir, "core", "infrastructure", "storage", "data", "migrations"
    )
    core_cfg.set_main_option("script_location", core_migrations_dir)

    # Set DB URL and metadata for injection
    from democrai.core.infrastructure.storage.data.models import Base

    db_url = get_current_db_url()
    core_cfg.set_main_option("sqlalchemy.url", db_url)

    # Injected attributes for env.py (prevents imports in env.py)
    core_cfg.attributes["target_metadata"] = Base.metadata
    core_cfg.attributes["db_url"] = db_url

    # Isolate version table for Data DB core
    core_cfg.set_main_option("version_table", "alembic_version_data")

    try:
        command.upgrade(core_cfg, "head")
        app_ctx().logger.info("[DATA DB] CORE migrations completed.")
    except Exception as e:
        app_ctx().logger.error(f"[DATA DB] CORE migration error: {e}")
        raise MigrationError(f"Data core migrations failed: {e}") from e

    # 2. Run PLUGIN migrations
    active_modules = _discover_module_migration_targets()
    app_ctx().logger.info(
        f"[DATA DB] Found {len(active_modules)} modules with migrations."
    )
    for module in active_modules:
        module_migrations_dir = os.path.join(module.path, "migrations")
        if os.path.exists(module_migrations_dir):
            app_ctx().logger.info(
                f"[DATA DB] Running migrations for module: {module.name} (Source: {module_migrations_dir})..."
            )

            # Create a dynamic config for the module
            module_cfg = Config()
            module_cfg.set_main_option("script_location", module_migrations_dir)
            module_cfg.set_main_option("sqlalchemy.url", db_url)

            # Use a separate version table for each module to avoid conflicts
            # This is set in the context of env.py, so we need a way to pass it.
            # We'll use 'x-argument' which is passed to env.py via context.configure
            module_cfg.set_main_option(
                "version_table", f"alembic_version_p_{module.name}"
            )
            module_cfg.attributes["target_metadata"] = _module_metadata(module)
            module_cfg.attributes["db_url"] = db_url
            module_cfg.attributes["include_object"] = _module_include_object(
                module.name
            )

            try:
                # We might need to ensure the module's migrations/env.py is aware of this
                # or we just use a standard env.py if provided by the module.
                # If the module doesn't have an env.py, we might want to provide a fallback.
                with module_database_context(module.name):
                    command.upgrade(module_cfg, "head")
                app_ctx().logger.info(
                    f"[DATA DB] Module {module.name} migrations completed."
                )
            except Exception as e:
                app_ctx().logger.error(
                    f"[DATA DB] Error in module {module.name} migrations: {e}"
                )
                raise MigrationError(
                    f"Data module migration failed for {module.name}: {e}"
                ) from e


class _ModuleMigrationTarget:
    def __init__(self, name: str, path: str, *, is_builtin: bool):
        self.name = name
        self.path = path
        self.is_builtin = is_builtin


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


def _module_include_object(module_name: str):
    prefix = f"p_{module_name}_"

    def include_object(object_, name, type_, reflected, compare_to):
        if type_ == "table":
            table_name = str(name or "")
        else:
            table_name = _object_table_name(object_, compare_to)
        if not table_name:
            return True
        return table_name.startswith(prefix)

    return include_object


def _module_model_import_candidates(module: _ModuleMigrationTarget) -> tuple[str, ...]:
    modules_dir = os.path.dirname(module.path)
    root_package = os.path.basename(modules_dir)
    candidates: list[str] = []
    if root_package:
        candidates.append(f"{root_package}.{module.name}.models")
    candidates.append(f"{module.name}.models")

    deduped: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        deduped.append(candidate)
    return tuple(deduped)


def _install_module_import_paths(module_path: str) -> list[str]:
    modules_dir = os.path.dirname(module_path)
    modules_parent = os.path.dirname(modules_dir)
    added_paths: list[str] = []
    for candidate in (modules_dir, modules_parent):
        if candidate and candidate not in sys.path:
            sys.path.insert(0, candidate)
            added_paths.append(candidate)
    return added_paths


def _is_builtin_module_path(module_path: str) -> bool:
    try:
        resolved_path = os.path.realpath(module_path)
    except Exception:
        return False
    for modules_dir in get_runtime_module_dirs():
        root = os.path.realpath(modules_dir)
        if resolved_path == root or resolved_path.startswith(root + os.sep):
            return True
    return False


def _module_metadata(module: _ModuleMigrationTarget) -> MetaData:
    import importlib

    added_paths = _install_module_import_paths(module.path)
    candidates = _module_model_import_candidates(module)
    last_missing: ImportError | None = None
    try:
        with module_database_context(module.name):
            for import_name in candidates:
                try:
                    models_module = importlib.import_module(import_name)
                    break
                except ModuleNotFoundError as exc:
                    missing_name = str(getattr(exc, "name", "") or "")
                    if missing_name in {
                        import_name,
                        import_name.rsplit(".", 1)[0],
                        import_name.split(".", 1)[0],
                    }:
                        last_missing = exc
                        continue
                    raise
            else:
                if last_missing is not None:
                    return MetaData()
                return MetaData()
    finally:
        for added_path in added_paths:
            try:
                sys.path.remove(added_path)
            except ValueError:
                pass

    module_base = getattr(models_module, "Base", None)
    source_metadata = getattr(module_base, "metadata", None)
    if source_metadata is None:
        return MetaData()
    metadata = MetaData()
    prefix = f"p_{module.name}_"
    for table in source_metadata.sorted_tables:
        if str(table.name).startswith(prefix):
            table.to_metadata(metadata)
    return metadata


def _discover_module_migration_targets() -> list[_ModuleMigrationTarget]:
    search_dirs = [(path, True) for path in get_runtime_module_dirs()]

    found: dict[str, _ModuleMigrationTarget] = {}
    for modules_dir, is_builtin in search_dirs:
        if not os.path.isdir(modules_dir):
            continue
        for entry in os.scandir(modules_dir):
            if not entry.is_dir():
                continue
            manifest_path = os.path.join(entry.path, "manifest.json")
            migrations_dir = os.path.join(entry.path, "migrations")
            if not os.path.isfile(manifest_path) or not os.path.isdir(migrations_dir):
                continue
            try:
                with open(manifest_path, "r", encoding="utf-8") as handle:
                    manifest = json.load(handle)
                module_name = validate_module_name(manifest.get("name"))
                if not normalize_bool(manifest.get("enabled"), default=True):
                    continue
            except Exception as exc:
                app_ctx().logger.warning(
                    f"[DATA DB] Skipping module migration discovery for {entry.path}: {exc}"
                )
                continue
            if module_name in found:
                continue
            found[module_name] = _ModuleMigrationTarget(
                module_name,
                entry.path,
                is_builtin=is_builtin,
            )

    return list(found.values())


def run_module_migration(module_name: str, module_path: str) -> None:
    """Utility to run migration for a specific module (e.g. at install/update time)."""
    module_migrations_dir = os.path.join(module_path, "migrations")
    if not os.path.exists(module_migrations_dir):
        return

    db_url = get_current_db_url()
    app_ctx().logger.info(
        f"[DATA DB] Running isolated migrations for module: {module_name}..."
    )

    module_cfg = Config()
    module_cfg.set_main_option("script_location", module_migrations_dir)
    module_cfg.set_main_option("sqlalchemy.url", db_url)

    # Enforce standard prefix for the version table to keep it in the module's namespace
    module_cfg.set_main_option("version_table", f"alembic_version_p_{module_name}")
    module = _ModuleMigrationTarget(
        module_name,
        module_path,
        is_builtin=_is_builtin_module_path(module_path),
    )
    module_cfg.attributes["target_metadata"] = _module_metadata(module)
    module_cfg.attributes["db_url"] = db_url
    module_cfg.attributes["include_object"] = _module_include_object(module_name)

    try:
        with module_database_context(module_name):
            command.upgrade(module_cfg, "head")
        app_ctx().logger.info(f"[DATA DB] Module {module_name} migrations completed.")
    except Exception as e:
        app_ctx().logger.error(
            f"[DATA DB] Error in module {module_name} migrations: {e}"
        )
        raise MigrationError(
            f"Isolated module migration failed for {module_name}: {e}"
        ) from e
