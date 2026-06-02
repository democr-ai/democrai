import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from democrai.core.infrastructure.database.sqlite_tuning import install_sqlite_engine_pragmas
from democrai.core.infrastructure.database.sqlite_tuning import sqlite_connect_args
from democrai.core.runtime.foundation.paths import get_data_dir
from democrai.core.runtime.foundation.app import app_ctx

# Backward compatibility for code that doesn't use AppContext.db yet
# This will be overridden by ctx.db in main.py

_default_engine = None
_default_SessionLocal = None
_db_url = None

def get_database_url() -> str:
    """
    Dynamically resolves the database connection URL.

    The URL is retrieved from the application config or falls back to a
    local SQLite file in the data directory.

    :return: The database connection URL string.
    """
    ctx = app_ctx()
    if ctx and ctx.config:
        url = ctx.config.get("database.url")
        if url:
            return url

    global _db_url
    if _db_url is None:
        DB_PATH = os.path.join(get_data_dir(), "democrai.db")
        _db_url = f"sqlite:///{DB_PATH}"
    return _db_url

# DEPRECATED: Accessing this at module level might return None or cause early init issues
DATABASE_URL = None # Will be set on first call to get_database_url if we want, but better to use function.

def _get_lazy_session():
    global _default_engine, _default_SessionLocal
    ctx = app_ctx()
    if bool(getattr(ctx, "setup_mode", False)) and not getattr(ctx, "db", None):
        raise RuntimeError("database_unavailable_in_setup_mode")
    if _default_SessionLocal is None:
        url = get_database_url()
        is_sqlite = url.startswith("sqlite")
        connect_args = sqlite_connect_args() if is_sqlite else {}
        _default_engine = create_engine(url, connect_args=connect_args)
        if is_sqlite:
            install_sqlite_engine_pragmas(_default_engine)
        _default_SessionLocal = scoped_session(
            sessionmaker(autocommit=False, autoflush=False, bind=_default_engine)
        )
    return _default_SessionLocal


def get_db():
    """
    FastAPI-compatible dependency that yields a database session.

    If the AppContext has a managed database service, it uses that;
    otherwise, it falls back to a lazy-initialized default session.
    """
    ctx = app_ctx()
    if ctx.db:
        db = ctx.db.get_session()
    else:
        db = _get_lazy_session()()

    try:
        yield db
    finally:
        db.close()


# For direct imports of SessionLocal (e.g. in older parts of the app)
class SessionLocalProxy:
    def __call__(self):
        ctx = app_ctx()
        if ctx.db:
            return ctx.db.get_session()
        return _get_lazy_session()()


SessionLocal = SessionLocalProxy()


def session_scope():
    """Context manager that yields a SQLAlchemy session and closes it on exit.

    Wraps sessions that don't natively support the context manager protocol,
    ensuring cleanup regardless of the session type returned by SessionLocal.
    """
    session = SessionLocal()
    if hasattr(session, "__enter__") and hasattr(session, "__exit__"):
        return session

    class _SessionScope:
        def __enter__(self_inner):
            return session

        def __exit__(self_inner, exc_type, exc, tb):
            close = getattr(session, "close", None)
            if callable(close):
                close()
            return False

    return _SessionScope()
