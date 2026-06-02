from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import sysconfig
import tempfile
from pathlib import Path
from typing import Any

from democrai.core.application.access_policy.manifest import AccessManifestRule
from democrai.core.application.access_policy.models import AccessResource
from democrai.core.application.access_policy.models import AccessSubject
from democrai.core.application.access_policy.operations import ResourceType
from democrai.core.application.ai.pipeline_context import current_ai_pipeline_context
from democrai.core.application.ai.pipeline_context import emit_ai_pipeline_event
from democrai.core.infrastructure.sandbox.os.helper import (
    apply_application_network_endpoints_with_helper,
    clear_application_network_allowlist_with_helper,
)
from democrai.core.infrastructure.sandbox.os.state import (
    is_application_network_allowlist_active,
)
from democrai.core.infrastructure.sandbox.process_guard import process_guard_context
from democrai.core.infrastructure.sandbox.process_guard import process_guard_bypass_context
from democrai.core.platform.agents.models import SkillDefinition
from democrai.core.platform.agents.registry import skill_registry


DEFAULT_TIMEOUT_SECONDS = 20
MAX_TIMEOUT_SECONDS = 120
MAX_OUTPUT_CHARS = 12000


async def run_skill_script(
    *,
    skill: str,
    script: str,
    args: list[str] | tuple[str, ...] | None = None,
    timeout_seconds: int | float | None = None,
) -> dict[str, Any]:
    raw_args = [] if args is None else list(args)
    resolved_args = tuple(str(item) for item in raw_args)
    await emit_ai_pipeline_event(
        type="skill.execution.started",
        name=skill,
        payload={"script": script, "args": list(resolved_args)},
    )
    try:
        result = await asyncio.to_thread(
            _run_skill_script_sync,
            skill=skill,
            script=script,
            args=resolved_args,
            timeout_seconds=timeout_seconds,
        )
    except Exception as exc:
        await emit_ai_pipeline_event(
            type="skill.execution.failed",
            name=skill,
            payload={"script": script, "error": str(exc)},
            status="error",
        )
        raise
    await emit_ai_pipeline_event(
        type="skill.execution.finished",
        name=skill,
        payload={"script": script, "result": result},
        status="ok",
    )
    return result


def _run_skill_script_sync(
    *,
    skill: str,
    script: str,
    args: tuple[str, ...],
    timeout_seconds: int | float | None,
) -> dict[str, Any]:
    definition = _resolve_selected_skill(skill)
    script_path = _resolve_script(definition, script)
    timeout = _timeout(timeout_seconds)
    ready_path = _network_ready_file()
    command = [
        sys.executable,
        str(Path(__file__).with_name("skill_script_child.py").resolve()),
        str(script_path),
        json.dumps(list(args), ensure_ascii=True),
    ]
    env = _script_env()
    env["DEMOCRAI_SKILL_SCRIPT_NETWORK_READY_FILE"] = str(ready_path)
    with process_guard_context(
        subject=definition.metadata.name,
        subject_kind="skill",
        access=_skill_script_access(definition, script_path, ready_path),
        include_runtime_access=False,
        inherit_parent_access=False,
    ):
        proc: subprocess.Popen[str] | None = None
        try:
            proc = subprocess.Popen(
                command,
                cwd=str(definition.root_dir),
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            _apply_skill_script_network_policy(proc.pid)
            ready_path.write_text("ready\n", encoding="utf-8")
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            if proc is not None:
                proc.kill()
                stdout, stderr = proc.communicate()
            else:
                stdout = exc.stdout if isinstance(exc.stdout, str) else ""
                stderr = exc.stderr if isinstance(exc.stderr, str) else ""
            return {
                "skill": definition.metadata.name,
                "script": _script_relative_path(definition, script_path),
                "returncode": None,
                "stdout": _truncate(stdout if isinstance(stdout, str) else ""),
                "stderr": _truncate(stderr if isinstance(stderr, str) else ""),
                "timed_out": True,
            }
        except BaseException:
            if proc is not None and proc.poll() is None:
                proc.kill()
                proc.communicate()
            raise
        finally:
            if proc is not None:
                _clear_skill_script_network_policy(proc.pid)
            try:
                ready_path.unlink()
            except OSError:
                pass
            try:
                ready_path.parent.rmdir()
            except OSError:
                pass
    return {
        "skill": definition.metadata.name,
        "script": _script_relative_path(definition, script_path),
        "returncode": int(proc.returncode if proc is not None else -1),
        "stdout": _truncate(stdout if isinstance(stdout, str) else ""),
        "stderr": _truncate(stderr if isinstance(stderr, str) else ""),
        "timed_out": False,
    }


def _resolve_selected_skill(name: str) -> SkillDefinition:
    resolved_name = name.strip() if isinstance(name, str) else ""
    if not resolved_name:
        raise ValueError("skill_required")
    context = current_ai_pipeline_context()
    selected = set(context.selected_skills if context is not None else ())
    if not selected or resolved_name not in selected:
        raise ValueError(f"skill_not_selected:{resolved_name}")
    definition = skill_registry.get(resolved_name)
    if definition is None:
        raise ValueError(f"skill_not_found:{resolved_name}")
    return definition


def _resolve_script(skill: SkillDefinition, value: str) -> Path:
    relative = value.strip().replace("\\", "/") if isinstance(value, str) else ""
    if not relative:
        raise ValueError("script_required")
    candidate_parts = Path(relative).parts
    if relative.startswith("/") or ".." in candidate_parts:
        raise ValueError("script_path_invalid")
    if relative not in skill.metadata.script_paths:
        raise ValueError(f"skill_script_not_found:{relative}")
    scripts_root = (skill.root_dir / "scripts").resolve()
    candidate = (scripts_root / relative).resolve()
    if not str(candidate).startswith(str(scripts_root)):
        raise ValueError("script_path_invalid")
    if candidate.suffix != ".py":
        raise ValueError("skill_script_unsupported_type")
    return candidate


def _script_relative_path(skill: SkillDefinition, script_path: Path) -> str:
    return script_path.relative_to((skill.root_dir / "scripts").resolve()).as_posix()


def _timeout(value: int | float | None) -> float:
    if value is None:
        return float(DEFAULT_TIMEOUT_SECONDS)
    return max(1.0, min(float(value), float(MAX_TIMEOUT_SECONDS)))


def _script_env() -> dict[str, str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith("DEMOCRAI_")
    }
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONNOUSERSITE"] = "1"
    app_root = Path(__file__).resolve().parents[3]
    raw_pythonpath = env.get("PYTHONPATH")
    current_pythonpath = raw_pythonpath.strip() if isinstance(raw_pythonpath, str) else ""
    env["PYTHONPATH"] = (
        str(app_root)
        if not current_pythonpath
        else os.pathsep.join([str(app_root), current_pythonpath])
    )
    return env


def _network_ready_file() -> Path:
    root = Path(tempfile.mkdtemp(prefix="democrai_skill_script_"))
    return root / "network.ready"


def _apply_skill_script_network_policy(pid: int) -> None:
    if not is_application_network_allowlist_active():
        return
    with process_guard_bypass_context():
        apply_application_network_endpoints_with_helper([], pid=int(pid))


def _clear_skill_script_network_policy(pid: int) -> None:
    if not is_application_network_allowlist_active():
        return
    try:
        with process_guard_bypass_context():
            clear_application_network_allowlist_with_helper(pid=int(pid))
    except Exception:
        pass


def _skill_script_access(
    skill: SkillDefinition,
    script_path: Path,
    ready_path: Path,
) -> tuple[AccessManifestRule, ...]:
    subject = AccessSubject.create("skill", skill.metadata.name)
    read_paths = [
        str(skill.root_dir.resolve()),
        str(Path(__file__).resolve().parents[3]),
        *_python_runtime_read_paths(),
    ]
    execute_paths = _path_variants(sys.executable)
    return (
        *_filesystem_rules(subject, "read", read_paths),
        *_filesystem_rules(subject, "execute", execute_paths),
        *_filesystem_rules(subject, "read", [str(script_path.resolve())]),
        *_filesystem_rules(subject, "create", [str(ready_path.parent.resolve())]),
        *_filesystem_rules(subject, "modify", [str(ready_path.parent.resolve())]),
        *_filesystem_rules(subject, "delete", [str(ready_path.parent.resolve())]),
    )


def _python_runtime_read_paths() -> list[str]:
    paths: list[str] = []
    for item in list(sys.path):
        if isinstance(item, str) and item.strip():
            paths.append(str(item))
    for key in ("stdlib", "platstdlib", "purelib", "platlib"):
        raw = sysconfig.get_paths().get(key)
        if isinstance(raw, str) and raw:
            paths.append(raw)
    for item in (sys.prefix, sys.exec_prefix, sys.base_prefix, sys.base_exec_prefix):
        raw = item.strip() if isinstance(item, str) else ""
        if raw:
            paths.append(raw)
    return paths


def _filesystem_rules(
    subject: AccessSubject,
    operation: str,
    paths: list[str],
) -> tuple[AccessManifestRule, ...]:
    rules: list[AccessManifestRule] = []
    seen: set[str] = set()
    for raw in paths:
        for path in _path_variants(raw):
            if not path or path in seen:
                continue
            seen.add(path)
            rules.append(
                AccessManifestRule(
                    subject=subject,
                    resource=AccessResource.create(
                        resource_type=ResourceType.FILESYSTEM,
                        operation=operation,
                        target=path,
                    ),
                )
            )
    return tuple(rules)


def _path_variants(value: object) -> list[str]:
    if isinstance(value, Path):
        resolved = value.expanduser()
    elif isinstance(value, str):
        raw = value.strip()
        if not raw:
            return []
        resolved = Path(raw).expanduser()
    else:
        return []
    variants = [
        str(resolved.absolute()),
        str(resolved.resolve()),
    ]
    deduped: list[str] = []
    seen: set[str] = set()
    for item in variants:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped


def _truncate(value: str) -> str:
    if len(value) <= MAX_OUTPUT_CHARS:
        return value
    return value[:MAX_OUTPUT_CHARS]
