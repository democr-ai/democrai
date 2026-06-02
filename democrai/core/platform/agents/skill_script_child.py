from __future__ import annotations

import json
import os
import runpy
import sys
import time
from pathlib import Path


def _apply_seccomp() -> None:
    if not sys.platform.startswith("linux"):
        return
    try:
        from democrai.core.infrastructure.sandbox.os.seccomp import (
            apply_seccomp_blocklist,
            is_seccomp_supported,
        )

        if is_seccomp_supported():
            apply_seccomp_blocklist()
    except Exception:
        return


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("skill_script_child_usage: script_path args_json")
    script_path = Path(sys.argv[1]).resolve()
    args = json.loads(sys.argv[2])
    if not isinstance(args, list):
        raise SystemExit("skill_script_child_args_must_be_list")
    raw_ready_path = os.environ.get("DEMOCRAI_SKILL_SCRIPT_NETWORK_READY_FILE")
    ready_path = raw_ready_path.strip() if isinstance(raw_ready_path, str) else ""
    if ready_path:
        deadline = time.monotonic() + 30.0
        while not Path(ready_path).exists():
            if time.monotonic() >= deadline:
                raise SystemExit("skill_script_child_network_ready_timeout")
            time.sleep(0.02)
    sys.argv = [str(script_path), *[str(item) for item in args]]
    _apply_seccomp()
    runpy.run_path(str(script_path), run_name="__main__")


if __name__ == "__main__":
    main()
