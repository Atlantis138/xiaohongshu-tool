@echo off
set "PROJECT_DIR=%~dp0.."
set "PYTHON=C:\Python\Python311\python.exe"

if exist "%PYTHON%" (
    "%PYTHON%" "%PROJECT_DIR%\xhs_scraper.py" %*
) else (
    python "%PROJECT_DIR%\xhs_scraper.py" %*
)
exit /b %ERRORLEVEL%
