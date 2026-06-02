from __future__ import annotations

from typing import Any

from democrai.core.application.ai.engine.config_crypto import decrypt_provider_config
from democrai.core.application.ai.engine.config_crypto import encrypt_provider_config
from democrai.core.infrastructure.database import SessionLocal
from democrai.core.infrastructure.database.models import EngineRegistry


def apply_engine_registry_config_updates(
    *,
    engine_id: str,
    updates: dict[str, Any] | None,
) -> None:
    if not updates:
        return
    with SessionLocal() as session:
        rows = (
            session.query(EngineRegistry)
            .filter(EngineRegistry.provider == engine_id)
            .all()
        )
        for row in rows:
            current = decrypt_provider_config(engine_id, row.config)
            current.update(updates)
            row.config = encrypt_provider_config(engine_id, current)
        session.commit()
