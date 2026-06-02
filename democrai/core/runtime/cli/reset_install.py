from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from urllib.parse import urlparse

from democrai.core.platform.config.yaml_config import YamlConfigProvider
from democrai.core.runtime.foundation.paths import get_data_dir


@dataclass(frozen=True)
class ResetTarget:
    key: str
    label: str
    path: str
    exists: bool
    sidecar_paths: tuple[str, ...] = ()


def _config_path() -> str:
    return os.path.join(get_data_dir(), "config.yaml")


def _desktop_jwt_path() -> str:
    return os.path.expanduser("~/.democrai/auth_token")


def _default_db_paths() -> dict[str, tuple[str, str]]:
    data_dir = get_data_dir()
    return {
        "db": ("Core DB", os.path.join(data_dir, "democrai.db")),
        "data": ("Data DB", os.path.join(data_dir, "data.db")),
        "kg": ("KG DB", os.path.join(data_dir, "kg.sqlite")),
        "vector": ("Vector DB", os.path.join(data_dir, "vector.db")),
        "observability": ("Observability DB", os.path.join(data_dir, "observability.db")),
    }


def _ladybug_sidecar_paths(db_path: str) -> tuple[str, ...]:
    return (f"{db_path}.wal",)


def _sqlite_sidecar_paths(db_path: str) -> tuple[str, ...]:
    return (f"{db_path}-wal", f"{db_path}-shm")


def _target_exists(db_path: str, sidecar_paths: tuple[str, ...] = ()) -> bool:
    return os.path.exists(db_path) or any(os.path.exists(path) for path in sidecar_paths)


def _sqlite_path_from_url(url: str | None) -> str | None:
    if not url:
        return None
    normalized = url.strip()
    if not normalized.startswith("sqlite:///"):
        return None
    parsed = urlparse(normalized)
    path = parsed.path or ""
    if parsed.netloc and not path.startswith("/"):
        path = f"/{path}"
    return path or None


def discover_reset_targets(config_path: str | None = None) -> tuple[str, list[ResetTarget]]:
    path = config_path or _config_path()
    defaults = _default_db_paths()
    if not os.path.exists(path):
        targets = []
        for key, (label, db_path) in defaults.items():
            sidecar_paths = _sqlite_sidecar_paths(db_path) if key == "kg" else ()
            exists = _target_exists(db_path, sidecar_paths)
            if exists:
                targets.append(
                    ResetTarget(
                        key=key,
                        label=label,
                        path=db_path,
                        exists=exists,
                        sidecar_paths=sidecar_paths,
                    )
                )
        return path, targets

    provider = YamlConfigProvider(path)
    targets: list[ResetTarget] = []

    def _append(
        key: str,
        label: str,
        db_path: str | None,
        sidecar_paths: tuple[str, ...] = (),
    ) -> None:
        if not db_path:
            return
        targets.append(
            ResetTarget(
                key=key,
                label=label,
                path=db_path,
                exists=_target_exists(db_path, sidecar_paths),
                sidecar_paths=sidecar_paths,
            )
        )

    db_type = str(provider.get("database.type", "sqlite")).strip().lower()
    db_url = provider.get("database.url")
    if db_type == "sqlite":
        _append("db", "Core DB", _sqlite_path_from_url(db_url) or defaults["db"][1])

    data_type = str(provider.get("database.data_type", db_type)).strip().lower()
    data_url = provider.get("database.data_url")
    if data_type == "sqlite":
        _append("data", "Data DB", _sqlite_path_from_url(data_url) or defaults["data"][1])

    kg_type = str(provider.get("storage.kg.type", "sqlite")).strip().lower()
    if kg_type == "ladybug":
        kg_path = provider.get("storage.kg.db_path")
        kg_db_path = str(kg_path or os.path.join(get_data_dir(), "kg.lbug"))
        _append("kg", "KG DB", kg_db_path, _ladybug_sidecar_paths(kg_db_path))
    if kg_type == "sqlite":
        kg_path = provider.get("storage.kg.db_path")
        kg_db_path = str(kg_path or defaults["kg"][1])
        _append("kg", "KG DB", kg_db_path, _sqlite_sidecar_paths(kg_db_path))

    vector_type = str(provider.get("storage.vector.type", "sqlite-vec")).strip().lower()
    if vector_type == "sqlite-vec":
        _append("vector", "Vector DB", defaults["vector"][1])

    obs_type = str(provider.get("storage.observability.type", "sqlite")).strip().lower()
    if obs_type == "sqlite":
        _append("observability", "Observability DB", defaults["observability"][1])

    deduped: dict[str, ResetTarget] = {}
    for target in targets:
        deduped[target.key] = target
    return path, list(deduped.values())


def discover_media_reset_target(config_path: str | None = None) -> ResetTarget | None:
    path = config_path or _config_path()
    default_media_path = os.path.join(get_data_dir(), "assets")
    if not os.path.exists(path):
        if os.path.exists(default_media_path):
            return ResetTarget(
                key="media",
                label="Media Storage",
                path=default_media_path,
                exists=True,
            )
        return None

    provider = YamlConfigProvider(path)
    media_type = str(provider.get("storage.media.type", "local")).strip().lower()
    if media_type != "local":
        return None

    media_path = provider.get("storage.media.path") or default_media_path
    return ResetTarget(
        key="media",
        label="Media Storage",
        path=media_path,
        exists=os.path.exists(media_path),
    )


def _confirm(prompt: str, *, input_fn=input) -> bool:
    answer = input_fn(f"{prompt} [y/N]: ").strip().lower()
    return answer in {"y", "yes"}


def _choose_targets(targets: list[ResetTarget], *, input_fn=input) -> list[ResetTarget]:
    existing = [target for target in targets if target.exists]
    if not existing:
        return []

    print("Detected local databases:")
    for index, target in enumerate(existing, start=1):
        print(f"  {index}. {target.label} -> {target.path}")

    raw = input_fn(
        "Which databases do you want to delete? Enter comma-separated numbers, 'all', or press Enter for none: "
    ).strip().lower()
    if not raw or raw == "none":
        return []
    if raw == "all":
        return existing

    chosen: list[ResetTarget] = []
    mapping = {str(index): target for index, target in enumerate(existing, start=1)}
    for item in [part.strip() for part in raw.split(",") if part.strip()]:
        target = mapping.get(item)
        if target and target not in chosen:
            chosen.append(target)
    return chosen


def _clear_desktop_jwt() -> str | None:
    token_path = _desktop_jwt_path()
    if not os.path.exists(token_path):
        return None
    os.remove(token_path)
    return token_path


def reset_installation(*, include_media: bool = False, input_fn=input) -> int:
    config_path, targets = discover_reset_targets()
    media_target = discover_media_reset_target(config_path) if include_media else None

    print("[RESET] This operation will remove the current config.yaml and return the application to setup mode.")
    print(f"[RESET] Current config: {config_path}")

    if not _confirm("Confirm installation reset?", input_fn=input_fn):
        print("[RESET] Operation cancelled.")
        return 1

    selected_targets = _choose_targets(targets, input_fn=input_fn)
    removed_paths: list[str] = []

    for target in selected_targets:
        target_paths = (target.path, *target.sidecar_paths)
        existing_paths = [path for path in target_paths if os.path.exists(path)]
        if not existing_paths:
            continue
        for path in existing_paths:
            os.remove(path)
            removed_paths.append(path)
        print(f"[RESET] Removed {target.label}: {target.path}")

    removed_media = False
    if include_media and media_target and media_target.exists:
        print(f"[RESET] Detected local media storage: {media_target.path}")
        if _confirm("Confirm local media deletion?", input_fn=input_fn):
            phrase = input_fn(
                "To confirm, type DELETE MEDIA and press Enter: "
            ).strip()
            if phrase == "DELETE MEDIA":
                shutil.rmtree(media_target.path)
                removed_media = True
                print(f"[RESET] Removed {media_target.label}: {media_target.path}")
            else:
                print("[RESET] Invalid media confirmation, media folder preserved.")
        else:
            print("[RESET] Media deletion cancelled.")
    elif include_media:
        print("[RESET] No local media storage to delete.")

    if os.path.exists(config_path):
        os.remove(config_path)
        print(f"[RESET] Removed config: {config_path}")
    else:
        print("[RESET] No config.yaml found.")

    removed_jwt = _clear_desktop_jwt()
    if removed_jwt:
        print(f"[RESET] Removed desktop JWT: {removed_jwt}")
    else:
        print("[RESET] No desktop JWT found.")

    if removed_paths:
        print(f"[RESET] Local databases removed: {len(removed_paths)}")
    else:
        print("[RESET] No local database deleted.")
    if include_media:
        if removed_media:
            print("[RESET] Local media removed.")
        else:
            print("[RESET] Local media preserved.")

    print("[RESET] Initial setup will run again on next startup.")
    return 0
