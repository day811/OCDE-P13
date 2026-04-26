#!/bin/bash
# app.sh - Launcher for the UI and environment setup

# Go to project root
cd "$(dirname "$0")"

# Export the current directory to PYTHONPATH so "import app" works
export PYTHONPATH="${PWD}"

echo "🎭 Launching Chainlit UI..."
chainlit run app/ui.py --port 8001