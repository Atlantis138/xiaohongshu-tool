@echo off
set "PROJECT_DIR=%~dp0.."
set "PYTHON=%PROJECT_DIR%\.venv\Scripts\python.exe"

if exist "%PYTHON%" (
    "%PYTHON%" "%PROJECT_DIR%\xhs_scraper.py" %*
) else (
    echo Project virtual environment not found.
    echo Run scripts\setup.ps1 from the project root first.
    exit /b 1
)
exit /b %ERRORLEVEL%
