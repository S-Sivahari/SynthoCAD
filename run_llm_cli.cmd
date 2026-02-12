@echo off
REM Launch a fresh cmd window and run the backend LLM CLI so you can type input there.
REM Works from the repo root. Uses the project's venv Python if present, otherwise system python.

SETLOCAL EnableDelayedExpansion
SET REPO_DIR=%~dp0
REM Trim trailing backslash if present
IF "%REPO_DIR:~-1%"=="\" SET REPO_DIR=%REPO_DIR:~0,-1%

SET VENV_PY="%REPO_DIR%\.venv\Scripts\python.exe"
IF EXIST %VENV_PY% (
  SET PY=%VENV_PY%
) ELSE (
  SET PY=python
)

REM Start a new cmd window and run the CLI (keeps window open for interactive input)
start "SynthoCAD LLM CLI" cmd /k "%PY% backend\llm_cli.py"

ENDLOCAL
