from __future__ import annotations

from typing import Any

from democrai.core.application.ai.engine.requirements import activation_requirements
from democrai.core.infrastructure.database import SessionLocal
from democrai.core.infrastructure.database.models import EngineRegistry


def _engine_registry_payload(row: EngineRegistry) -> dict[str, Any]:
    return {
        "engine_registry_id": row.id,
        "provider": row.provider,
        "status": row.status,
        "supported": row.supported,
    }


async def activate_engine_instance(engine_registry_id: int) -> dict[str, Any]:
    """Activate an engine registry row and synchronize the runtime."""
    requirements = await activation_requirements(engine_registry_id=engine_registry_id)
    if not requirements.get("ready"):
        return {
            **requirements,
            "status": "",
            "activation_ready": False,
        }

    with SessionLocal() as session:
        row = (
            session.query(EngineRegistry)
            .filter(EngineRegistry.id == engine_registry_id)
            .first()
        )
        if row is None:
            return {
                "ready": False,
                "reason": "engine_registry_row_not_found",
                "engine_registry_id": engine_registry_id,
                "provider": "",
                "provider_label": "",
                "supported": False,
                "requires_config": False,
                "missing_dependencies": [],
                "activation_message": "engine_registry_row_not_found",
                "status": "",
                "activation_ready": False,
            }
        row.status = "active"
        row.supported = True
        session.commit()
        payload = _engine_registry_payload(row)

    from democrai.core.application.ai.engine.orchestrator.client import (
        EngineOrchestratorClient,
    )
    from democrai.core.application.ai.engine.runtime import get_engine_runtime
    import os

    if os.environ.get("DEMOCRAI_ENGINE_ORCHESTRATOR") != "1":
        EngineOrchestratorClient().sync_active_engines()
    else:
        await get_engine_runtime().sync_active_engines()
    return {
        **requirements,
        **payload,
        "ready": True,
        "activation_ready": True,
        "activation_message": "",
    }


async def deactivate_engine_instance(engine_registry_id: int) -> dict[str, Any]:
    """Deactivate an engine registry row and synchronize the runtime."""
    with SessionLocal() as session:
        row = (
            session.query(EngineRegistry)
            .filter(EngineRegistry.id == engine_registry_id)
            .first()
        )
        if row is None:
            return {
                "ready": False,
                "reason": "engine_registry_row_not_found",
                "engine_registry_id": engine_registry_id,
                "provider": "",
                "status": "",
                "supported": False,
            }
        row.status = "installed"
        session.commit()
        payload = _engine_registry_payload(row)

    from democrai.core.application.ai.engine.orchestrator.client import (
        EngineOrchestratorClient,
    )
    from democrai.core.application.ai.engine.runtime import get_engine_runtime
    import os

    if os.environ.get("DEMOCRAI_ENGINE_ORCHESTRATOR") != "1":
        EngineOrchestratorClient().sync_active_engines()
    else:
        await get_engine_runtime().sync_active_engines()
    return {
        **payload,
        "ready": True,
        "reason": "",
    }
