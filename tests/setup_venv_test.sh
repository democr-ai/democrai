#!/bin/bash

set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# Create venv if it doesn't exist
if [ ! -d "tests/.venv_test" ]; then
    echo "Creating virtual environment..."
    python3 -m venv tests/.venv_test
else
    echo "Virtual environment already exists."
fi

echo "Activating virtual environment..."
source tests/.venv_test/bin/activate

echo "Upgrading base packaging tools..."
python3 -m pip install --upgrade pip setuptools wheel

echo "Installing lightweight base requirements..."
python3 -m pip install -r requirements-dev.txt -c constraints.txt

echo "Setup complete. To run tests:"
echo "source tests/.venv_test/bin/activate"
echo "pytest -c tests/pytest.ini tests/runtime"
