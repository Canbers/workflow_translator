#!/bin/bash
# Quick setup script for workflow_translator
set -e

echo "[1/4] Checking Python..."
python3 --version || { echo "Python 3 is required."; exit 1; }

echo "[2/4] Creating virtual environment (.venv) if missing..."
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi

echo "[3/4] Activating virtual environment..."
source .venv/bin/activate

echo "[4/4] Installing dependencies..."
pip install -q -r requirements.txt || {
  echo "Falling back to install 'requests' directly...";
  pip install -q requests;
}

if [ ! -f .env ] && [ -f .env.example ]; then
  cp .env.example .env
  echo "Created .env from .env.example. Please open .env and fill SIS_API_KEY and SIS_WORKFLOW_ID."
fi

echo ""
echo "Environment ready. The script auto-loads your .env; no need to export vars."
echo "Common commands:"
echo "  python3 sis_translate_workflow.py --self-test                 # Safe demo"
echo "  python3 sis_translate_workflow.py                             # Dry run (uses .env)"
echo "  python3 sis_translate_workflow.py --write                     # Apply changes"
echo "  python3 sis_translate_workflow.py --log-level DEBUG           # Verbose logs"
echo ""
echo "To deactivate later: deactivate"
