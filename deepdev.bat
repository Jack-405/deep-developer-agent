@echo off

set "DEEPDEV_ROOT=%~dp0"
set "DEEPDEV_PY=%DEEPDEV_ROOT%.venv\Scripts\python.exe"

if not exist "%DEEPDEV_PY%" (
    echo [deepdev] Error: Python interpreter not found:
    echo %DEEPDEV_PY%
    echo [deepdev] Please run uv sync in the deep-developer-agent directory.
    exit /b 1
)

set "PYTHONPATH=%DEEPDEV_ROOT%;%PYTHONPATH%"

"%DEEPDEV_PY%" -m cli %*

exit /b %ERRORLEVEL%