#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

PYTHON_CMD=""

find_python() {
    if command -v py >/dev/null 2>&1 && py -3.12 -c "import sys" >/dev/null 2>&1; then
        PYTHON_CMD="py -3.12"
    elif command -v python3.12 >/dev/null 2>&1; then
        PYTHON_CMD="python3.12"
    elif command -v python3 >/dev/null 2>&1 && python3 -c "import sys; raise SystemExit(sys.version_info < (3, 12))" >/dev/null 2>&1; then
        PYTHON_CMD="python3"
    elif command -v python >/dev/null 2>&1 && python -c "import sys; raise SystemExit(sys.version_info < (3, 12))" >/dev/null 2>&1; then
        PYTHON_CMD="python"
    fi
}

run_as_root() {
    if command -v sudo >/dev/null 2>&1; then
        sudo "$@"
    else
        "$@"
    fi
}

install_python() {
    echo "Python 3.12+ not found. Trying to install Python 3.12..."
    OS_NAME=$(uname -s 2>/dev/null || printf unknown)

    if [ "$OS_NAME" = "Darwin" ]; then
        if ! command -v brew >/dev/null 2>&1; then
            echo "Homebrew is required to install Python automatically on macOS." >&2
            return 1
        fi
        brew install python@3.12
    elif [ "$OS_NAME" = "Linux" ]; then
        if command -v apt-get >/dev/null 2>&1; then
            run_as_root apt-get update
            run_as_root apt-get install -y python3.12 python3.12-venv
        elif command -v dnf >/dev/null 2>&1; then
            run_as_root dnf install -y python3.12
        elif command -v yum >/dev/null 2>&1; then
            run_as_root yum install -y python3.12
        elif command -v zypper >/dev/null 2>&1; then
            run_as_root zypper install -y python312 python312-venv
        elif command -v pacman >/dev/null 2>&1; then
            run_as_root pacman -S --needed --noconfirm python
        elif command -v apk >/dev/null 2>&1; then
            run_as_root apk add python3 py3-virtualenv
        else
            echo "No supported Linux package manager found." >&2
            return 1
        fi
    elif command -v winget.exe >/dev/null 2>&1; then
        winget.exe install --id Python.Python.3.12 -e --source winget
    else
        echo "No supported Python installer found for this platform." >&2
        return 1
    fi
}

find_python
if [ -z "$PYTHON_CMD" ]; then
    install_python
    find_python
fi

if [ -n "$PYTHON_CMD" ]; then
    # PYTHON_CMD is assigned only from fixed command names above.
    exec $PYTHON_CMD "$SCRIPT_DIR/run.py" "$@"
fi

echo "Python 3.12+ not found." >&2
exit 1
