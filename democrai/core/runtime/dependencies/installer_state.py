from __future__ import annotations

import json
from pathlib import Path


def state_file(target: Path) -> Path:
    return target / ".deps_state.json"


def load_state(target: Path) -> dict:
    path = state_file(target)
    if not path.exists():
        return {"deps": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"deps": {}}


def save_state(target: Path, state: dict) -> None:
    path = state_file(target)
    path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
