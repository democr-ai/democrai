import os
from typing import Any

import yaml

from modules.system.utils.ui.setup.config import (
    apply_config_payload,
    build_local_setup_config,
    load_yaml_payload_bytes,
    validate_distributed_setup_payload,
)


def _normalize_setup_upload(raw: Any) -> dict[str, Any]:
    candidate = raw if isinstance(raw, dict) else {}
    path = str(
        candidate.get("storage_path")
        or candidate.get("path")
        or candidate.get("source_path")
        or ""
    ).strip()
    return {
        "path": path,
        "name": str(
            candidate.get("name") or os.path.basename(path) or "config.yaml"
        ).strip()
        or "config.yaml",
        "mime": str(
            candidate.get("mime")
            or candidate.get("type")
            or "application/octet-stream"
        ).strip()
        or "application/octet-stream",
        "file_id": str(candidate.get("file_id") or "").strip(),
        "raw": dict(candidate),
    }


def _validation_status(
    upload_meta: dict[str, Any],
    *,
    errors: list[str],
    warnings: list[str],
    validated: bool,
) -> str:
    config_path = str(
        upload_meta.get("name") or upload_meta.get("path") or ""
    ).strip()
    if not config_path:
        return "No YAML file selected."

    lines = [f"Selected file: {config_path}"]
    if validated:
        lines.append("Validation status: ok")
    elif errors or warnings:
        lines.append("Validation status: invalid")
    else:
        lines.append("Validation status: pending")

    if warnings:
        lines.append("")
        lines.append("Warnings:")
        lines.extend(f"- {message}" for message in warnings)

    if errors:
        lines.append("")
        lines.append("Errors:")
        lines.extend(f"- {message}" for message in errors)

    return "\n".join(lines)


def _set_validation_state(
    state_values: dict[str, Any],
    upload_meta: dict[str, Any],
    *,
    payload: dict | None,
    errors: list[str],
    warnings: list[str],
) -> bool:
    validated = not errors
    state_values["/system/setup/config_validation_errors"] = errors
    state_values["/system/setup/config_validation_warnings"] = warnings
    state_values["/system/setup/config_validated"] = validated
    state_values["/system/setup/distributed_config_payload"] = (
        (payload or {}) if validated else {}
    )
    state_values["/system/setup/config_validation_status"] = _validation_status(
        upload_meta,
        errors=errors,
        warnings=warnings,
        validated=validated,
    )
    return validated


async def validate_distributed_config(
    module_sdk,
    *,
    upload_item: Any,
    state_values: dict[str, Any],
) -> bool:
    upload_meta = _normalize_setup_upload(upload_item)
    upload_path = str(upload_meta.get("path") or "").strip()
    if not upload_path:
        return _set_validation_state(
            state_values,
            upload_meta,
            payload=None,
            errors=["Devi selezionare un file config YAML."],
            warnings=[],
        )

    try:
        if upload_path.startswith("media/"):
            payload_bytes = module_sdk.media.view(upload_path)
        else:
            with open(upload_path, "rb") as fh:
                payload_bytes = fh.read()
        payload = load_yaml_payload_bytes(payload_bytes)
    except yaml.YAMLError as exc:
        return _set_validation_state(
            state_values,
            upload_meta,
            payload=None,
            errors=[f"YAML non valido: {exc}"],
            warnings=[],
        )
    except Exception as exc:
        return _set_validation_state(
            state_values,
            upload_meta,
            payload=None,
            errors=[f"Impossibile leggere il file caricato: {exc}"],
            warnings=[],
        )

    payload, result = validate_distributed_setup_payload(
        payload,
        source_label=upload_path,
    )
    return _set_validation_state(
        state_values,
        upload_meta,
        payload=payload,
        errors=[item.message for item in result.errors],
        warnings=[item.message for item in result.warnings],
    )


async def finalize_setup(
    module_sdk,
    *,
    install_mode: str,
    admin_user: str,
    admin_email: str,
    admin_pass: str,
    payload: dict | None,
    media_path: str | None,
    stream_id: str | None = None,
    session_key: str | None = None,
):
    from democrai.sdk.system import app_ctx

    if install_mode == "distributed":
        if not payload:
            raise ValueError("Distributed configuration is invalid or missing.")
        config_payload = payload
    else:
        config_payload = build_local_setup_config(media_path or "")

    cfg = app_ctx().config
    apply_config_payload(cfg, config_payload)
    cfg.save()
    module_sdk.system.log(
        "[Setup] Configuration saved. Requesting core finalization...",
        "info",
    )

    await module_sdk.system.setup.request_finalize(
        admin_user,
        admin_pass,
        admin_email=admin_email,
        stream_id=stream_id,
        session_key=session_key,
    )
