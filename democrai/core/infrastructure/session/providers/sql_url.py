from __future__ import annotations

import json

from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, create_engine, select, Text
from sqlalchemy.orm import sessionmaker

from democrai.core.infrastructure.database.sqlite_tuning import install_sqlite_engine_pragmas
from democrai.core.infrastructure.database.sqlite_tuning import sqlite_connect_args
from democrai.core.platform.utils.timezone import utc_now_naive


class SqlUrlJsonStore:
    def __init__(self, database_url: str, table_name: str) -> None:
        connect_args = sqlite_connect_args() if database_url.startswith("sqlite:///") else {}
        self._engine = create_engine(database_url, connect_args=connect_args)
        if database_url.startswith("sqlite:///"):
            install_sqlite_engine_pragmas(self._engine)
        self._metadata = MetaData()
        self._table = Table(
            table_name,
            self._metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("session_key", String(255), nullable=False, unique=True, index=True),
            Column("data", Text, nullable=False),
            Column(
                "updated_at",
                DateTime,
                nullable=False,
                default=utc_now_naive,
                onupdate=utc_now_naive,
            ),
        )
        self._metadata.create_all(self._engine)
        self._SessionLocal = sessionmaker(
            bind=self._engine, autocommit=False, autoflush=False
        )

    def load(self, key: str) -> dict[str, object] | None:
        with self._SessionLocal() as session:
            row = session.execute(
                select(self._table.c.data).where(self._table.c.session_key == key)
            ).first()
            if row is None:
                return None
            value = json.loads(row[0])
            return value if isinstance(value, dict) else None

    def save(self, key: str, value: dict[str, object]) -> None:
        payload = json.dumps(value, default=str)
        with self._SessionLocal() as session:
            existing = session.execute(
                select(self._table.c.id).where(self._table.c.session_key == key)
            ).first()
            if existing is None:
                session.execute(
                    self._table.insert().values(session_key=key, data=payload)
                )
            else:
                session.execute(
                    self._table.update()
                    .where(self._table.c.session_key == key)
                    .values(data=payload, updated_at=utc_now_naive())
                )
            session.commit()

    def delete(self, key: str) -> None:
        with self._SessionLocal() as session:
            session.execute(
                self._table.delete().where(self._table.c.session_key == key)
            )
            session.commit()

    def keys(self) -> list[str]:
        with self._SessionLocal() as session:
            rows = session.execute(select(self._table.c.session_key)).all()
            return [str(row[0]) for row in rows]
