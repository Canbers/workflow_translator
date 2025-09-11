#!/bin/bash
# Activation script for workflow_translator
# This script activates the virtual environment and provides helpful commands

echo "Activating workflow_translator environment..."
source .venv/bin/activate

echo "Environment activated! Available commands:"
echo "  python sis_translate_workflow.py --help          # Show help"
echo "  python sis_translate_workflow.py --self-test     # Run self-test"
echo "  python sis_translate_workflow.py --workflow ID   # Run on specific workflow"
echo ""
echo "To deactivate, run: deactivate"
echo ""

# Keep the shell active
exec bash
