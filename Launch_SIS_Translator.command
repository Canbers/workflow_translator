#!/bin/bash

# SIS Workflow Translator - Mac Launcher
# Double-click this file to launch the Streamlit GUI

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "Starting SIS Workflow Translator..."
echo "Directory: $SCRIPT_DIR"

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo "Virtual environment not found. Running setup..."
    if [ -f "activate.sh" ]; then
        bash activate.sh
    else
        echo "Error: activate.sh not found. Please run setup manually."
        echo "Press any key to exit..."
        read -n 1
        exit 1
    fi
fi

# Activate virtual environment
echo "Activating virtual environment..."
source .venv/bin/activate

# Check if Streamlit is installed
if ! python -c "import streamlit" 2>/dev/null; then
    echo "Installing dependencies..."
    pip install -r requirements.txt
fi

# Launch Streamlit app
echo "Launching Streamlit app..."
echo "The app will open in your default web browser."
echo "If it doesn't open automatically, go to: http://localhost:8501"
echo ""
echo "Press Ctrl+C to stop the app when you're done."
echo ""

streamlit run streamlit_app.py

echo ""
echo "App stopped. Press any key to exit..."
read -n 1
