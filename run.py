from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from setup_venv import ensure_environment


ROOT = Path(__file__).resolve().parent


def main() -> int:
    venv_python = ensure_environment()
    command = [str(venv_python), str(ROOT / "main.py"), *sys.argv[1:]]
    return subprocess.call(command, cwd=ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
