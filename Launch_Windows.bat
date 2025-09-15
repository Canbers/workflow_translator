@echo off
REM SIS Workflow Translator - Windows Launcher
REM Double-click this file to launch the Streamlit GUI

echo Starting SIS Workflow Translator...

REM Get the directory where this script is located
set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

echo Directory: %SCRIPT_DIR%

REM Check if virtual environment exists
if not exist ".venv" (
    echo Virtual environment not found. Running setup...
    if exist "activate.bat" (
        call activate.bat
    ) else (
        echo Error: activate.bat not found. Please run setup manually.
        echo Press any key to exit...
        pause >nul
        exit /b 1
    )
)

REM Activate virtual environment
echo Activating virtual environment...
call .venv\Scripts\activate.bat

REM Check if Streamlit is installed
python -c "import streamlit" >nul 2>&1
if errorlevel 1 (
    echo Installing dependencies...
    pip install -r src/requirements.txt
)

REM Launch Streamlit app
echo Launching Streamlit app...
echo The app will open in your default web browser.
echo If it doesn't open automatically, go to: http://localhost:8501
echo.
echo Press Ctrl+C to stop the app when you're done.
echo.

streamlit run src/streamlit_app.py

echo.
echo App stopped. Press any key to exit...
pause >nul
