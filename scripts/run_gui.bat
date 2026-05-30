@echo off
set "PROJECT_DIR=%~dp0.."
set "PYTHONW=C:\Python\Python311\pythonw.exe"
set "PYTHON=C:\Python\Python311\python.exe"

if exist "%PYTHONW%" (
    "%PYTHONW%" "%PROJECT_DIR%\xhs_gui.py"
) else if exist "%PYTHON%" (
    "%PYTHON%" "%PROJECT_DIR%\xhs_gui.py"
) else (
    python "%PROJECT_DIR%\xhs_gui.py"
)
