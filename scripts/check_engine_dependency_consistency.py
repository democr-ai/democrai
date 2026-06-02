#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"invalid json: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"invalid json object: {path}")
    return payload


def _covered_module(module_name: str, declared_modules: set[str]) -> bool:
    if module_name in declared_modules:
        return True
    base = module_name.split(".")[0]
    return any(
        declared == base
        or declared.startswith(base + ".")
        or base.startswith(declared + ".")
        for declared in declared_modules
    )


def _engine_issues(engine_dir: Path) -> list[str]:
    manifest_path = engine_dir / "manifest.json"
    engine_path = engine_dir / "engine.py"
    if not manifest_path.exists() or not engine_path.exists():
        return []

    manifest = _load_json(manifest_path)
    deps = manifest.get("provider", {}).get("dependencies") or []
    if not isinstance(deps, list):
        deps = []

    dependency_keys = {
        str(dep.get("dependency_key") or "").strip()
        for dep in deps
        if isinstance(dep, dict) and str(dep.get("dependency_key") or "").strip()
    }
    dependency_modules = {
        str(dep.get("module") or "").strip()
        for dep in deps
        if isinstance(dep, dict) and str(dep.get("module") or "").strip()
    }

    source = engine_path.read_text(encoding="utf-8")
    install_keys = set(re.findall(r'install_dependency\("([^"]+)"', source))
    ensure_keys = set(
        re.findall(r'ensure_import\([^\n]*dependency_key="([^"]+)"', source)
    )

    check_modules: set[str] = set()
    for args in re.findall(r"_missing_modules\((.*?)\)", source, flags=re.S):
        check_modules.update(re.findall(r'\("([^"]+)",\s*"[^"]+"\)', args))

    issues: list[str] = []
    not_in_manifest = sorted(key for key in install_keys if key not in dependency_keys)
    if not_in_manifest:
        issues.append(f"_install uses dependency keys not in manifest: {not_in_manifest}")

    not_in_manifest = sorted(key for key in ensure_keys if key not in dependency_keys)
    if not_in_manifest:
        issues.append(
            "ensure_import uses dependency keys not in manifest: "
            f"{not_in_manifest}"
        )

    missing_modules = sorted(
        module
        for module in check_modules
        if not _covered_module(module, dependency_modules)
    )
    if missing_modules:
        issues.append(
            "_check_ready references modules not declared in manifest dependencies: "
            f"{missing_modules}"
        )

    return issues


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    engines_root = project_root / "engines"
    if not engines_root.exists():
        print("engines directory not found", file=sys.stderr)
        return 2

    all_issues: list[tuple[str, list[str]]] = []
    for engine_dir in sorted(p for p in engines_root.iterdir() if p.is_dir()):
        issues = _engine_issues(engine_dir)
        if issues:
            all_issues.append((engine_dir.name, issues))

    if not all_issues:
        print("OK: no engine dependency inconsistencies found.")
        return 0

    print("FAILED: engine dependency inconsistencies found:")
    for engine_name, issues in all_issues:
        print(f"[{engine_name}]")
        for issue in issues:
            print(f" - {issue}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
