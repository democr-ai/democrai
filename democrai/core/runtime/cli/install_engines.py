from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

import yaml

from democrai.core.application.ai.engine.config_install import (
    EngineInstallConfigError,
    install_engines_config_audit_metadata,
    install_engines_from_config,
    reset_full_engine_state_before_runtime_start,
)
from democrai.core.runtime.entrypoint import (
    core_runtime_options_from_args,
    start_core_runtime,
)
from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.runtime.foundation.app import request_context_scope
from democrai.core.runtime.lifecycle.cleanup import run_shutdown_cleanup


def install_engines(
    *,
    config_path: str,
    reset_mode: str,
    yes: bool,
    json_output: bool,
    args,
) -> int:
    try:
        config = _load_yaml_config(config_path)
    except EngineInstallConfigError as exc:
        _print_error(str(exc), json_output=json_output)
        return 2

    runtime_started = False
    try:
        if reset_mode == "full":
            reset_full_engine_state_before_runtime_start(
                yes=yes,
                args=args,
                progress=lambda event: _print_progress(event, json_output=json_output),
            )
        _print_progress({"phase": "runtime", "status": "starting"}, json_output=json_output)
        start_core_runtime(core_runtime_options_from_args(args))
        runtime_started = True
        if bool(getattr(app_ctx(), "setup_mode", False)):
            _print_error(
                "install-engines requires an existing application configuration",
                json_output=json_output,
            )
            return 2
        _print_progress({"phase": "runtime", "status": "started"}, json_output=json_output)
        _record_command_audit(
            config=config,
            config_path=config_path,
            reset_mode=reset_mode,
            json_output=json_output,
        )

        from democrai.sdk.client import active_sdk as sdk

        with request_context_scope(_install_engines_request_context_payload()):
            report = asyncio.run(
                install_engines_from_config(
                    sdk,
                    config,
                    reset_mode=reset_mode,
                    yes=True if reset_mode == "full" else yes,
                    progress=lambda event: _print_progress(event, json_output=json_output),
                )
            )
    except EngineInstallConfigError as exc:
        _print_error(str(exc), json_output=json_output)
        return 2
    except Exception as exc:
        _print_error(f"runtime_error:{exc}", json_output=json_output)
        return 2
    finally:
        if runtime_started:
            run_shutdown_cleanup(app_ctx(), reloader=None, child_proc=None)

    payload = report.to_dict()
    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        _print_report(payload)
    return 1 if report.has_errors() else 0


def _load_yaml_config(path: str) -> dict[str, Any]:
    resolved = Path(os.path.expanduser(str(path or ""))).resolve()
    if not resolved.exists():
        raise EngineInstallConfigError(f"config_not_found:{path}")
    if not resolved.is_file():
        raise EngineInstallConfigError(f"config_not_file:{path}")
    try:
        with resolved.open("r", encoding="utf-8") as handle:
            payload = yaml.safe_load(handle)
    except OSError as exc:
        raise EngineInstallConfigError(f"config_not_readable:{path}:{exc}") from exc
    except yaml.YAMLError as exc:
        raise EngineInstallConfigError(f"yaml_invalid:{exc}") from exc
    if not isinstance(payload, dict):
        raise EngineInstallConfigError("config_must_be_mapping")
    return payload


def _install_engines_request_context_payload() -> dict[str, Any]:
    return {
        "request_id": "cli.install-engines",
        "user": 0,
        "role": "core",
        "organization_id": None,
        "access_level": 3,
        "channel": "cli",
        "action_name": "install-engines",
        "module_name": "core",
    }


def _record_command_audit(
    *,
    config: dict[str, Any],
    config_path: str,
    reset_mode: str,
    json_output: bool,
) -> None:
    ctx = app_ctx()
    store = getattr(ctx, "observability_store", None)
    if store is None:
        return
    metadata = {
        "command": "install-engines",
        "config_path": config_path,
        "reset_mode": reset_mode,
        "json_output": bool(json_output),
        "providers": [],
        "engine_count": 0,
    }
    try:
        metadata.update(install_engines_config_audit_metadata(config))
    except Exception as exc:
        metadata["config_summary_error"] = str(exc)
    try:
        store.record_audit_event(
            event_type="cli_command",
            actor_user_id=0,
            actor_role="core",
            channel="cli",
            entity_type="runtime_command",
            entity_id="install-engines",
            operation="install-engines",
            status="started",
            before={},
            after={},
            metadata=metadata,
        )
    except Exception as exc:
        print(f"[warning] audit_not_recorded:{exc}", file=sys.stderr)


def _print_progress(event: dict[str, Any], *, json_output: bool) -> None:
    phase = str(event.get("phase") or "").strip()
    status = str(event.get("status") or "").strip()
    message = str(event.get("message") or "").strip()
    provider = str(event.get("provider") or "").strip()
    engine_name = str(event.get("engine_name") or "").strip()
    model_id = str(event.get("model_id") or "").strip()

    if phase == "engine":
        subject = engine_name or provider or "engine"
        line = f"[engine {subject}] {status}"
    elif phase == "model":
        subject = model_id or "model"
        line = f"[model {subject}] {status}"
    elif phase == "reset":
        line = f"[reset] mode={status}" if status in {"keep", "selected", "full"} else f"[reset] {status}"
    else:
        line = f"[{phase or 'install-engines'}] {status}"
    if message:
        line = f"{line}: {message}"
    print(line, file=sys.stderr if json_output else sys.stdout)


def _print_error(message: str, *, json_output: bool) -> None:
    if json_output:
        print(
            json.dumps({"status": "error", "error": message}, indent=2, sort_keys=True),
            file=sys.stderr,
        )
        return
    print(f"[error] {message}", file=sys.stderr)


def _print_report(payload: dict[str, Any]) -> None:
    engines = payload.get("engines") if isinstance(payload.get("engines"), dict) else {}
    models = payload.get("models") if isinstance(payload.get("models"), dict) else {}
    engine_errors = engines.get("errors") if isinstance(engines.get("errors"), list) else []
    model_errors = models.get("errors") if isinstance(models.get("errors"), list) else []
    print(
        "[summary] "
        f"engines installed={len(engines.get('installed') or [])} "
        f"active={len(engines.get('activated') or [])} "
        f"models downloaded={len(models.get('downloaded') or [])} "
        f"active={len(models.get('activated') or [])} "
        f"errors={len(engine_errors) + len(model_errors)}"
    )
    for error in [*engine_errors, *model_errors]:
        if error.get("kind") == "engine":
            print(
                f"[engine {error.get('engine_name') or error.get('provider')}] error: {error.get('error')}"
            )
        else:
            print(f"[model {error.get('model_id')}] error: {error.get('error')}")
