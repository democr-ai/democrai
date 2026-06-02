from sqlalchemy import engine_from_config
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
