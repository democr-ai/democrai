import sys
import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# Try to get metadata and URL from injected attributes (Decoupled mode)
config = context.config
injected_metadata = config.attributes.get("target_metadata")
injected_url = config.attributes.get("db_url")

if injected_metadata and injected_url:
    target_metadata = injected_metadata
    DATABASE_URL = injected_url
else:
    # Standard import mode (Developer / CLI)
    try:
        from democrai.core.infrastructure.storage.observability.models import Base
        from democrai.core.runtime.foundation.paths import get_data_dir

        DB_PATH = os.path.join(get_data_dir(), "observability.db")
        DATABASE_URL = f"sqlite:///{DB_PATH}"
        target_metadata = Base.metadata
    except ImportError:
        # Add application root to path if running via CLI 'alembic' in dev
        # path is: [root]/core/infrastructure/storage/observability/migrations/env.py -> 6 levels up
        parent_dir = os.path.dirname(
            os.path.dirname(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            )
        )
        if parent_dir not in sys.path:
            sys.path.insert(0, parent_dir)
        from democrai.core.infrastructure.storage.observability.models import Base
        from democrai.core.runtime.foundation.paths import get_data_dir

        DB_PATH = os.path.join(get_data_dir(), "observability.db")
        DATABASE_URL = f"sqlite:///{DB_PATH}"
        target_metadata = Base.metadata

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Set sqlalchemy.url dynamically
config.set_main_option("sqlalchemy.url", DATABASE_URL)

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    # fileConfig(config.config_file_name)
    pass

# target_metadata is set during initialization above


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
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

    with connectable.connect() as connection:
        with connection.begin():
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                render_as_batch=True,
                transactional_ddl=True,
                transaction_per_migration=False,
            )

            with context.begin_transaction():
                context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
