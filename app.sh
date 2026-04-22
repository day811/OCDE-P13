#!/bin/bash
# run_app.sh - Launch Streamlit application

echo "🎭 Launching Streamlit Application..."
echo "=========================================="
echo ""
echo "Opening http://localhost:8501 in your browser..."
echo "Press Ctrl+C to stop the server"
echo ""
echo "=========================================="
echo ""

cd "$(dirname "$0")"          # ← Va à la racine du projet
export PYTHONPATH="${PWD}"    # ← Ajoute la racine au PYTHONPATH

streamlit run src/main.py \
    --logger.level=info \
    --client.showErrorDetails=true 