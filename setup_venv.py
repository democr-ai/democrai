from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
REQUIREMENTS = ROOT / "requirements.txt"
CONSTRAINTS = ROOT / "constraints.txt"
SETUP_MARKER = VENV / ".democrai_setup_complete"
MIN_PYTHON = (3, 12)


def _check_python_version() -> None:
    if sys.version_info < MIN_PYTHON:
        required = ".".join(str(part) for part in MIN_PYTHON)
        current = ".".join(str(part) for part in sys.version_info[:3])
        raise SystemExit(f"Python {required}+ is required; found Python {current}")


def _venv_python() -> Path:
    if os.name == "nt":
        return VENV / "Scripts" / "python.exe"
    return VENV / "bin" / "python"


def _run(command: list[str]) -> None:
    subprocess.check_call(command, cwd=ROOT)


def _dependency_inputs() -> list[Path]:
    return [path for path in (REQUIREMENTS, CONSTRAINTS, ROOT / "setup_venv.py") if path.exists()]


def _dependencies_are_ready() -> bool:
    if not SETUP_MARKER.exists():
        return False
    marker_mtime = SETUP_MARKER.stat().st_mtime
    return all(path.stat().st_mtime <= marker_mtime for path in _dependency_inputs())


def ensure_environment() -> Path:
    _check_python_version()

    venv_python = _venv_python()
    if not venv_python.exists():
        print("Creating virtual environment...")
        _run([sys.executable, "-m", "venv", str(VENV)])
    else:
        print("Virtual environment already exists.")

    if _dependencies_are_ready():
        print("Dependencies already installed.")
        return venv_python

    print("Upgrading base packaging tools...")
    _run([str(venv_python), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"])

    print("Installing lightweight base requirements...")
    _run([str(venv_python), "-m", "pip", "install", "-r", str(REQUIREMENTS), "-c", str(CONSTRAINTS)])

    SETUP_MARKER.write_text("ok\n", encoding="utf-8")
    return venv_python


def main() -> int:
    venv_python = ensure_environment()
    print("Setup complete. To run the app:")
    if os.name == "nt":
        print(r".venv\Scripts\python.exe main.py")
    else:
        print(".venv/bin/python main.py")
    print(f"Resolved Python: {venv_python}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
