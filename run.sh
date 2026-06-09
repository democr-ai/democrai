#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

PYTHON_CMD=""

find_python() {
    if command -v py >/dev/null 2>&1 && py -3.12 -c "import sys" >/dev/null 2>&1; then
        PYTHON_CMD="py -3.12"
    elif command -v python3.12 >/dev/null 2>&1; then
        PYTHON_CMD="python3.12"
    elif command -v python3 >/dev/null 2>&1 && python3 -c "import sys; v=sys.version_info[:2]; raise SystemExit(not ((3,12)<=v<(3,14)))" >/dev/null 2>&1; then
        PYTHON_CMD="python3"
    elif command -v python >/dev/null 2>&1 && python -c "import sys; v=sys.version_info[:2]; raise SystemExit(not ((3,12)<=v<(3,14)))" >/dev/null 2>&1; then
        PYTHON_CMD="python"
    fi
}

find_uv_python() {
    _uv_cmd=""
    if command -v uv >/dev/null 2>&1; then
        _uv_cmd="uv"
    elif [ -x "$HOME/.local/bin/uv" ]; then
        _uv_cmd="$HOME/.local/bin/uv"
    elif [ -x "$HOME/.cargo/bin/uv" ]; then
        _uv_cmd="$HOME/.cargo/bin/uv"
    fi
    if [ -n "$_uv_cmd" ]; then
        _uv_python=$("$_uv_cmd" python find 3.12 2>/dev/null || true)
        if [ -n "$_uv_python" ] && [ -x "$_uv_python" ]; then
            PYTHON_CMD="$_uv_python"
        fi
    fi
}

_ensure_uv() {
    if command -v uv >/dev/null 2>&1; then
        return 0
    fi
    if [ -x "$HOME/.local/bin/uv" ] || [ -x "$HOME/.cargo/bin/uv" ]; then
        export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
        return 0
    fi
    echo "Installing uv..."
    if command -v curl >/dev/null 2>&1; then
        curl -LsSf https://astral.sh/uv/install.sh | sh
    elif command -v wget >/dev/null 2>&1; then
        wget -qO- https://astral.sh/uv/install.sh | sh
    else
        echo "curl or wget required to install uv." >&2
        return 1
    fi
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
    if ! command -v uv >/dev/null 2>&1; then
        echo "uv installation failed." >&2
        return 1
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
        if _ensure_uv; then
            echo "Installing Python 3.12 via uv..."
            uv python install 3.12
        else
            echo "uv is required to install Python automatically on macOS." >&2
            return 1
        fi
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
    find_uv_python
fi
if [ -z "$PYTHON_CMD" ]; then
    install_python
    find_python
    if [ -z "$PYTHON_CMD" ]; then
        find_uv_python
    fi
fi

if [ -n "$PYTHON_CMD" ]; then
    # PYTHON_CMD is assigned only from fixed command names above or from uv python find.
    exec $PYTHON_CMD "$SCRIPT_DIR/run.py" "$@"
fi

echo "Python 3.12+ not found." >&2
exit 1
