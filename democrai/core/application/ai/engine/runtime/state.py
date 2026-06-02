from __future__ import annotations

from democrai.core.infrastructure.database import SessionLocal
from democrai.core.infrastructure.database.models import EngineRegistry


def active_engine_registry_rows() -> list[EngineRegistry]:
    with SessionLocal() as session:
        return (
            session.query(EngineRegistry)
            .filter(EngineRegistry.status == "active")
            .all()
        )


def is_compile_failure(error: Exception) -> bool:
    error_text = str(error)
    return "Failed to compile" in error_text or "[Compile::" in error_text


def mark_engine_compile_failure(engine_row_id: int) -> None:
    with SessionLocal() as session:
        row = (
            session.query(EngineRegistry)
            .filter(EngineRegistry.id == engine_row_id)
            .first()
        )
        if row is None:
            return
        row.status = "error"
        row.supported = False
        session.commit()
