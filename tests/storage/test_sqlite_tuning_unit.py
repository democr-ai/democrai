from __future__ import annotations

from types import SimpleNamespace

from democrai.core.infrastructure.database import sqlite_tuning as mod


def test_sqlite_connect_args_and_pragmas_application():
    executed = []
    closed = []

    class _Cursor:
        def execute(self, stmt):
            executed.append(stmt)

        def close(self):
            closed.append(True)

    class _Conn:
        def cursor(self):
            return _Cursor()

    args = mod.sqlite_connect_args(timeout_seconds=1.5)
    assert args == {"check_same_thread": False, "timeout": 1.5}

    mod.apply_sqlite_pragmas_to_connection(
        _Conn(),
        busy_timeout_ms=321,
        wal_autocheckpoint_pages=123,
        journal_size_limit_bytes=456,
    )
    assert "PRAGMA journal_mode=WAL" in executed
    assert "PRAGMA synchronous=NORMAL" in executed
    assert "PRAGMA wal_autocheckpoint=123" in executed
    assert "PRAGMA journal_size_limit=456" in executed
    assert "PRAGMA busy_timeout=321" in executed
    assert "PRAGMA temp_store=MEMORY" in executed
    assert closed == [True]


def test_install_sqlite_engine_pragmas_handles_connection_without_cursor(monkeypatch):
    listeners = {}
    applied = []

    def _listens_for(_engine, signal):
        assert signal == "connect"

        def _decorator(fn):
            listeners["fn"] = fn
            return fn

        return _decorator

    monkeypatch.setattr(mod.event, "listens_for", _listens_for)
    monkeypatch.setattr(mod, "apply_sqlite_pragmas_to_connection", lambda conn, busy_timeout_ms=5000: applied.append((conn, busy_timeout_ms)))

    mod.install_sqlite_engine_pragmas(object(), busy_timeout_ms=777)
    conn_with_cursor = SimpleNamespace(cursor=lambda: object())
    listeners["fn"](conn_with_cursor, None)
    listeners["fn"](object(), None)

    assert applied == [(conn_with_cursor, 777)]
