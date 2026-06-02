#!/usr/bin/env python3
import os
import sys

app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if app_dir not in sys.path:
    sys.path.insert(0, app_dir)


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python scripts/install_system_dependency.py <dependency_key>")
        return 1

    dep_key = str(sys.argv[1]).strip().lower()
    if not dep_key:
        print("Dependency key cannot be empty.")
        return 1

    try:
        from democrai.core.runtime.dependencies.system_dependencies import install_dependency

        install_dependency(dep_key)
        print(f"[+] Installed system dependency: {dep_key}")
        return 0
    except Exception as exc:
        print(f"[!] Failed to install system dependency '{dep_key}': {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
