@echo off
setlocal EnableDelayedExpansion

set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

echo.
echo ============================================
echo   ARIA -- Standalone Local AI
echo ============================================
echo.

:: ── Python check ───────────────────────────────────────────────────────────
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python not found.
    echo Download it from https://python.org  (check "Add to PATH" during install^)
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo [OK] %%v

:: ── Virtual environment ────────────────────────────────────────────────────
if not exist ".venv" (
    echo [--] Creating virtual environment...
    python -m venv .venv
)
call .venv\Scripts\activate.bat

:: ── Install / upgrade deps ─────────────────────────────────────────────────
echo [--] Checking dependencies...
pip install -q -r requirements.txt
echo [OK] Dependencies ready

:: ── Check model exists ─────────────────────────────────────────────────────
for /f %%c in ('python -c "import json,pathlib; cfg=json.load(open('config.json')); p=pathlib.Path(cfg.get('model_path','')).expanduser(); print('yes' if p.exists() else 'no')" 2^>nul') do set MODEL_OK=%%c

if "%MODEL_OK%"=="no" (
    echo.
    echo [!!] No model file found.
    echo      Run: python download_model.py
    echo      to download a model, then try again.
    echo.
    set /p DOWNLOAD="Download a model now? [Y/n]: "
    if /i not "%DOWNLOAD%"=="n" (
        python download_model.py
    ) else (
        pause
        exit /b 1
    )
)

:: ── Data directories ───────────────────────────────────────────────────────
if not exist "models"           mkdir models
if not exist "data\knowledge"   mkdir data\knowledge
if not exist "data\uploads"     mkdir data\uploads
if not exist "data\sessions"    mkdir data\sessions

:: ── Get port ───────────────────────────────────────────────────────────────
for /f %%p in ('python -c "import json; print(json.load(open('config.json')).get('port', 7860))" 2^>nul') do set PORT=%%p
if "%PORT%"=="" set PORT=7860

echo.
echo [--] Starting ARIA on http://localhost:%PORT%
echo      Model loads on first message (may take 10-30s the first time^)
echo      Press Ctrl+C to stop
echo.

python app.py
