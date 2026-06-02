#!/bin/bash

# Create venv if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
else
    echo "Virtual environment already exists."
fi

echo "Activating virtual environment..."
source .venv/bin/activate

echo "Upgrading base packaging tools..."
python3 -m pip install --upgrade pip setuptools wheel

echo "Installing lightweight base requirements..."
python3 -m pip install -r requirements.txt -c constraints.txt

echo "Setup complete. To run the app:"
echo "source .venv/bin/activate"
echo "python main.py"
