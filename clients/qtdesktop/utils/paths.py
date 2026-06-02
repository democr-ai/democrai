from __future__ import annotations

import os
import sys
from pathlib import Path


def get_desktop_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return str(Path(__file__).resolve().parents[1])


def get_assets_dir() -> str:
    return str(Path(get_desktop_dir()) / "assets")


def resolve_resource(resource_path: str) -> str:
    if not resource_path or not isinstance(resource_path, str):
        return resource_path

    if resource_path.startswith(("http://", "https://", "ric.", "<svg")):
        return resource_path

    candidate = Path(resource_path).expanduser()
    if candidate.is_absolute():
        return str(candidate)

    normalized = str(resource_path).strip().lstrip("./").replace("\\", "/")
    if normalized.startswith("clients/qtdesktop/assets/"):
        normalized = normalized[len("clients/qtdesktop/assets/") :]
    elif normalized.startswith("assets/"):
        normalized = normalized[len("assets/") :]

    assets_dir = Path(get_assets_dir())
    resolved = (assets_dir / normalized).resolve()
    if resolved.exists():
        return str(resolved)
    return resource_path


__all__ = [
    "get_assets_dir",
    "get_desktop_dir",
    "resolve_resource",
]
