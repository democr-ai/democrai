from __future__ import annotations

from typing import Any

from democrai.core.application.models import CoreModelContext, build_core_model


def get_engine_runtime_config(*, engine_row_id: int) -> dict[str, Any]:
    model = build_core_model(
        "engine_registry",
        CoreModelContext(
            user_id=0,
            organization_id=None,
            access_level=1,
            module_name="democrai.core.ai.engine_runtime",
            session={},
            bypass=True,
        ),
    )
    row = model.view(engine_row_id)
    if not isinstance(row, dict):
        raise RuntimeError(f"engine_registry_row_not_found:{engine_row_id}")
    config = row.get("config")
    if not isinstance(config, dict):
        raise RuntimeError(f"engine_registry_config_invalid:{engine_row_id}")
    return dict(config)
