from __future__ import annotations

import asyncio
import getpass
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

import yaml

from democrai.core.application.setup.config_payload import (
    apply_config_payload,
    validate_distributed_setup_payload,
)
from democrai.core.runtime.entrypoint import (
    core_runtime_options_from_args,
    start_core_runtime,
)
from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.runtime.lifecycle.cleanup import run_shutdown_cleanup


class SetupCommandError(ValueError):
    pass


_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def setup_application(
    *,
    config_path: str,
    yes: bool,
    json_output: bool,
    args,
) -> int:
    try:
        payload = _load_yaml_config(config_path)
        admin, config_payload = _validate_setup_payload(payload)
    except SetupCommandError as exc:
        _print_error(str(exc), json_output=json_output)
        return 2

    if not admin["password"]:
        try:
            admin["password"] = _prompt_admin_password(json_output=json_output)
        except SetupCommandError as exc:
            _print_error(str(exc), json_output=json_output)
            return 2

    try:
        _print_progress("config", "validating", json_output=json_output)
        normalized_config, validation = validate_distributed_setup_payload(
            config_payload,
            source_label=config_path,
        )
        if not validation.ok:
            _print_error(_format_validation_errors(validation), json_output=json_output)
            return 2
        if not _confirm_setup(yes=yes):
            _print_error("setup_cancelled", json_output=json_output)
            return 2
    except SetupCommandError as exc:
        _print_error(str(exc), json_output=json_output)
        return 2

    runtime_started = False
    try:
        _print_progress("runtime", "starting setup runtime", json_output=json_output)
        start_core_runtime(core_runtime_options_from_args(args))
        runtime_started = True
        ctx = app_ctx()
        if not bool(getattr(ctx, "setup_mode", False)):
            _print_error(
                "setup_requires_missing_runtime_config",
                json_output=json_output,
            )
            return 2

        cfg = getattr(ctx, "config", None)
        if cfg is None:
            _print_error("runtime_config_provider_unavailable", json_output=json_output)
            return 2
        apply_config_payload(cfg, normalized_config)
        cfg.save()
        _print_progress("config", "saved", json_output=json_output)

        _print_progress("setup", "finalizing", json_output=json_output)
        _request_setup_finalize(
            admin=admin,
            timeout_seconds=120.0,
        )
        _print_progress("admin", "created", json_output=json_output)
        runtime_started = False
    except SetupCommandError as exc:
        _print_error(str(exc), json_output=json_output)
        return 2
    except Exception as exc:
        _print_error(f"setup_finalize_failed:{exc}", json_output=json_output)
        return 1
    finally:
        if runtime_started:
            run_shutdown_cleanup(app_ctx(), reloader=None, child_proc=None)

    report = {
        "status": "ok",
        "config_path": str(getattr(app_ctx().config, "config_path", "") or ""),
        "admin": {
            "username": admin["username"],
            "email": admin["email"],
        },
        "setup_mode": bool(getattr(app_ctx(), "setup_mode", False)),
    }
    if json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        _print_progress("summary", "setup completed", json_output=json_output)
    return 0


def _request_setup_finalize(
    *,
    admin: dict[str, str],
    timeout_seconds: float,
) -> None:
    ctx = app_ctx()
    network = getattr(ctx, "network", None)
    loop = getattr(network, "_loop", None)
    if loop is None or not loop.is_running():
        raise SetupCommandError("runtime_loop_unavailable")

    from democrai.sdk.client import active_sdk as sdk

    future = asyncio.run_coroutine_threadsafe(
        sdk.system.setup.request_finalize(
            admin["username"],
            admin["password"],
            admin_email=admin["email"] or None,
        ),
        loop,
    )
    future.result(timeout=10.0)

    deadline = time.monotonic() + max(0.0, timeout_seconds)
    while time.monotonic() < deadline:
        if not bool(getattr(app_ctx(), "setup_mode", False)):
            return
        time.sleep(0.1)
    raise SetupCommandError("setup_finalize_timeout")


def _load_yaml_config(path: str) -> dict[str, Any]:
    resolved = Path(os.path.expanduser(str(path or ""))).resolve()
    if not resolved.exists():
        raise SetupCommandError(f"config_not_found:{path}")
    if not resolved.is_file():
        raise SetupCommandError(f"config_not_file:{path}")
    try:
        with resolved.open("r", encoding="utf-8") as handle:
            payload = yaml.safe_load(handle)
    except OSError as exc:
        raise SetupCommandError(f"config_not_readable:{path}:{exc}") from exc
    except yaml.YAMLError as exc:
        raise SetupCommandError(f"yaml_invalid:{exc}") from exc
    if not isinstance(payload, dict):
        raise SetupCommandError("setup_yaml_must_be_mapping")
    return payload


def _validate_setup_payload(payload: dict[str, Any]) -> tuple[dict[str, str], dict[str, Any]]:
    admin_payload = payload.get("admin")
    config_payload = payload.get("config")
    if not isinstance(admin_payload, dict):
        raise SetupCommandError("admin_must_be_mapping")
    if not isinstance(config_payload, dict) or not config_payload:
        raise SetupCommandError("config_must_be_non_empty_mapping")

    username = _expand_admin_value(admin_payload.get("username"), "admin.username").strip()
    email = _expand_admin_value(admin_payload.get("email", ""), "admin.email").strip()
    password = _expand_admin_value(admin_payload.get("password", ""), "admin.password")
    if not username:
        raise SetupCommandError("admin.username_required")
    return {
        "username": username,
        "email": email,
        "password": password,
    }, config_payload


def _expand_admin_value(value: Any, field_name: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)

    def _replace(match: re.Match[str]) -> str:
        env_name = match.group(1)
        if env_name not in os.environ:
            raise SetupCommandError(f"env_missing:{field_name}:{env_name}")
        return os.environ[env_name]

    return _ENV_PATTERN.sub(_replace, value)


def _prompt_admin_password(*, json_output: bool) -> str:
    if not sys.stdin.isatty():
        raise SetupCommandError("admin.password_required_without_tty")
    print("[admin] password required", file=sys.stderr if json_output else sys.stdout)
    password = getpass.getpass("Admin password: ")
    if not password.strip():
        raise SetupCommandError("admin.password_required")
    confirm = getpass.getpass("Confirm admin password: ")
    if password != confirm:
        raise SetupCommandError("admin.password_confirmation_mismatch")
    return password


def _confirm_setup(*, yes: bool) -> bool:
    if yes:
        return True
    if not sys.stdin.isatty():
        raise SetupCommandError("setup_confirmation_required_without_tty")
    answer = input("Proceed with initial setup? [y/N]: ").strip().lower()
    return answer in {"y", "yes"}


def _format_validation_errors(validation) -> str:
    errors = getattr(validation, "errors", []) or []
    messages = [str(getattr(item, "message", item)) for item in errors]
    return "config_invalid:" + "; ".join(messages)


def _print_progress(phase: str, message: str, *, json_output: bool) -> None:
    print(f"[{phase}] {message}", file=sys.stderr if json_output else sys.stdout)


def _print_error(message: str, *, json_output: bool) -> None:
    if json_output:
        print(
            json.dumps({"status": "error", "error": message}, indent=2, sort_keys=True),
            file=sys.stderr,
        )
        return
    print(f"[error] {message}", file=sys.stderr)
