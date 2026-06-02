from __future__ import annotations

import sqlite3
from typing import Any

from sqlalchemy import event


def sqlite_connect_args(*, timeout_seconds: float = 5.0) -> dict[str, Any]:
    return {
        "check_same_thread": False,
        "timeout": timeout_seconds,
    }


def apply_sqlite_pragmas_to_connection(
    connection: sqlite3.Connection,
    *,
    busy_timeout_ms: int = 5000,
    wal_autocheckpoint_pages: int = 1000,
    journal_size_limit_bytes: int = 268435456,
) -> None:
    cursor = connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute(f"PRAGMA wal_autocheckpoint={wal_autocheckpoint_pages}")
        cursor.execute(f"PRAGMA journal_size_limit={journal_size_limit_bytes}")
        cursor.execute(f"PRAGMA busy_timeout={busy_timeout_ms}")
        cursor.execute("PRAGMA temp_store=MEMORY")
    finally:
        cursor.close()


def install_sqlite_engine_pragmas(engine, *, busy_timeout_ms: int = 5000) -> None:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, _connection_record):
        if hasattr(dbapi_connection, "cursor"):
            apply_sqlite_pragmas_to_connection(
                dbapi_connection,
                busy_timeout_ms=busy_timeout_ms,
            )
