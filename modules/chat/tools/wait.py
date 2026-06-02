from __future__ import annotations

import asyncio
from typing import Any

from democrai.sdk.decorators import tool


@tool(
    "wait-seconds",
    title="Wait briefly",
    description="Wait a bounded number of seconds before checking async ingestion again.",
    input_schema={
        "type": "object",
        "properties": {
            "seconds": {
                "type": "number",
                "minimum": 0,
                "maximum": 60,
                "default": 2,
            }
        },
    },
)
async def wait_seconds(
    seconds: int | float | str = 2, *, context: dict[str, Any] | None = None
) -> dict[str, Any]:
    duration = max(0.0, min(60.0, float(seconds or 0)))
    await asyncio.sleep(duration)
    return {"status": "ok", "waited_seconds": duration, "context": dict(context or {})}
