#!/bin/bash
set -e

# Detect GPU presence (CUDA)
if command -v nvidia-smi &> /dev/null; then
    echo "[Installer] NVIDIA GPU detected. Compiling llama-cpp-python with CUDA support..."
    # Set flags for CUDA compilation
    export CMAKE_ARGS="-DGGML_CUDA=ON"
    export FORCE_CMAKE=1
else
    echo "[Installer] No NVIDIA GPU detected. Installing standard llama-cpp-python (CPU only)..."
fi

# Determine Python path
PYTHON_PATH="../.venv/bin/python3"
if [ ! -f "$PYTHON_PATH" ]; then
    PYTHON_PATH="python3"
fi

echo "[Installer] Installing dependencies..."
$PYTHON_PATH -m pip install llama-cpp-python vllm

echo "[Installer] Installation complete."
