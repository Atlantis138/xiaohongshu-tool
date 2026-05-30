@echo off
set "PROJECT_DIR=%~dp0.."
set "PYTHONW=%PROJECT_DIR%\.venv\Scripts\pythonw.exe"
set "PYTHON=%PROJECT_DIR%\.venv\Scripts\python.exe"

if exist "%PYTHONW%" (
    "%PYTHONW%" "%PROJECT_DIR%\xhs_gui.py"
) else if exist "%PYTHON%" (
    "%PYTHON%" "%PROJECT_DIR%\xhs_gui.py"
) else (
    echo Project virtual environment not found.
    echo Run scripts\setup.ps1 from the project root first.
    exit /b 1
)
