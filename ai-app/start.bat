@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo.
echo   ARIA -- Starting...
echo.

:: ── Python ──────────────────────────────────────────────────────────────────
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python not found. Run install.bat first.
    pause & exit /b 1
)

:: ── Venv ─────────────────────────────────────────────────────────────────────
if not exist ".venv\Scripts\activate.bat" (
    echo [--] No virtual environment found. Running setup...
    call install.bat
    exit /b
)
call .venv\Scripts\activate.bat

:: ── Quick dep check ──────────────────────────────────────────────────────────
python -c "import fastapi, uvicorn, llama_cpp" >nul 2>&1
if %errorlevel% neq 0 (
    echo [--] Missing dependencies. Installing...
    pip install -q -r requirements.txt
    pip install llama-cpp-python --prefer-binary --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu -q
)

:: ── Check model ───────────────────────────────────────────────────────────────
python -c "import json,pathlib; cfg=json.load(open('config.json')); p=pathlib.Path(cfg.get('model_path','')); exit(0 if p.exists() else 1)" >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo [!!] No model file found.
    set /p DL="Download one now? [Y/n]: "
    if /i not "!DL!"=="n" python download_model.py
)

:: ── Data dirs ─────────────────────────────────────────────────────────────────
if not exist "models"         mkdir models
if not exist "data\knowledge" mkdir data\knowledge
if not exist "data\uploads"   mkdir data\uploads
if not exist "data\sessions"  mkdir data\sessions

:: ── Launch ────────────────────────────────────────────────────────────────────
echo [--] Launching ARIA window...
python launcher.py
