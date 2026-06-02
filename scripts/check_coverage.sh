#!/bin/bash
# Script per il controllo granulare della copertura dei test

# Assicurati di essere nel venv o usa il path assoluto
VENV_PATH="${HOME}/Progetti/Democrai/.venv/bin/activate"
if [ -f "$VENV_PATH" ]; then
    source "$VENV_PATH"
fi

echo "--- 🚀 Esecuzione Test e Generazione Coverage ---"
pytest --cov=core --cov=desktop --cov-report=

echo -e "\n--- 🧠 Verifica CORE (Target: 92%) ---"
coverage report --include="core/*" --fail-under=95

CORE_STATUS=$?

echo -e "\n--- 🎨 Verifica DESKTOP (Target: 40% - Best Effort) ---"
coverage report --include="clients/qtdesktop/*" --fail-under=40

DESKTOP_STATUS=$?

if [ $CORE_STATUS -ne 0 ]; then
    echo -e "\n❌ ERRORE: La copertura del CORE è sotto il 92%!"
    exit 1
fi

echo -e "\n✅ Check completato con successo!"
