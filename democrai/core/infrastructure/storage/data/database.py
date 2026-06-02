import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from democrai.core.infrastructure.database.sqlite_tuning import install_sqlite_engine_pragmas
from democrai.core.infrastructure.database.sqlite_tuning import sqlite_connect_args
from democrai.core.runtime.foundation.paths import get_data_dir
from democrai.core.runtime.foundation.app import app_ctx

def get_database_url():
    """Returns the database URL from config or environment."""
    ctx = app_ctx()
    if ctx and ctx.config:
        # Check config first
        url = ctx.config.get("database.data_url") or ctx.config.get("database.url")
        if url:
            return url

    # Fallback to env or default
    # We compute default lazily to ensure safe path resolution
    data_db_path = os.path.join(get_data_dir(), "data.db")
    default_url = f"sqlite:///{data_db_path}"
    return os.getenv("DEMOCRAI_DATA_URL", default_url)


# DEPRECATED: Access via get_database_url()
DATABASE_URL = None

# For SQLite, we might need check_same_thread=False
# We can't check variable content here, so we assume sqlite if not configured otherwise or check inside lazy init
_engine = None
_SessionLocal = None

def _get_lazy_session():
    global _engine, _SessionLocal
    if _SessionLocal is None:
        url = get_database_url()
        is_sqlite = url.startswith("sqlite")
        connect_args = sqlite_connect_args() if is_sqlite else {}
        _engine = create_engine(url, connect_args=connect_args)
        if is_sqlite:
            install_sqlite_engine_pragmas(_engine)
        _SessionLocal = scoped_session(
            sessionmaker(autocommit=False, autoflush=False, bind=_engine)
        )
    return _SessionLocal


def get_data_db():
    db = _get_lazy_session()()
    try:
        yield db
    finally:
        db.close()
