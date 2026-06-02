from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CoreModelContext:
    user_id: int
    organization_id: int | None
    access_level: int
    module_name: str
    session: dict[str, Any]
    bypass: bool = False

