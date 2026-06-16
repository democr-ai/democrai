from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any


async def put_with_backpressure(
    queue: asyncio.Queue,
    item: Any,
    *,
    is_active: Callable[[], bool],
    check_interval_seconds: float = 0.25,
) -> bool:
    while is_active():
        try:
            await asyncio.wait_for(
                queue.put(item),
                timeout=max(0.01, float(check_interval_seconds)),
            )
            return True
        except asyncio.TimeoutError:
            continue
    return False
