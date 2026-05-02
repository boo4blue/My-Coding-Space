@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo.
echo ============================================
echo   ARIA -- Setup (Windows)
echo ============================================
echo.

:: ── Python ─────────────────────────────────────────────────────────────────
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [!!] Python not found.
    echo      1. Go to https://python.org/downloads
    echo      2. Download Python 3.11 or newer
    echo      3. During install: CHECK "Add Python to PATH"
    echo      4. Re-run this script
    start https://python.org/downloads
    pause & exit /b 1
)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo [OK] %%v

:: ── Venv ────────────────────────────────────────────────────────────────────
if not exist ".venv" (
    echo [--] Creating virtual environment...
    python -m venv .venv
)
call .venv\Scripts\activate.bat
echo [OK] Virtual environment ready

:: ── Core deps (no compiler required) ───────────────────────────────────────
echo [--] Installing dependencies...
pip install -q --upgrade pip
pip install -q -r requirements.txt
echo [OK] Core dependencies installed

:: ── llama-cpp-python (pre-built wheel, no Visual Studio needed) ─────────────
echo.
echo [--] Installing AI engine (llama-cpp-python)...
echo      Using pre-built binary -- no Visual Studio required.
echo.

pip install llama-cpp-python --prefer-binary --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu -q

if %errorlevel% neq 0 (
    echo [--] First method failed, trying PyPI binary...
    pip install llama-cpp-python --prefer-binary -q
)

if %errorlevel% neq 0 (
    echo.
    echo [!!] Auto-install failed. Manual steps:
    echo      1. Go to: https://github.com/abetlen/llama-cpp-python/releases/latest
    echo      2. Download the .whl matching your Python (cp311=3.11, cp312=3.12) for win_amd64
    echo      3. Run: .venv\Scripts\pip install path\to\the\file.whl
    echo.
    pause
) else (
    echo [OK] AI engine installed
)

:: ── GPU option ──────────────────────────────────────────────────────────────
echo.
set /p GPU="Do you have an NVIDIA GPU? Want faster AI? [y/N]: "
if /i "!GPU!"=="y" (
    echo [--] Installing CUDA version...
    pip install llama-cpp-python --prefer-binary --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu121 --force-reinstall -q
    if !errorlevel! equ 0 (
        python -c "import json; cfg=json.load(open('config.json')); cfg['n_gpu_layers']=-1; json.dump(cfg,open('config.json','w'),indent=2)"
        echo [OK] GPU mode enabled
    ) else (
        echo [!!] CUDA install failed -- staying on CPU mode
    )
)

:: ── Data dirs ────────────────────────────────────────────────────────────────
if not exist "models"         mkdir models
if not exist "data\knowledge" mkdir data\knowledge
if not exist "data\uploads"   mkdir data\uploads
if not exist "data\sessions"  mkdir data\sessions

:: ── Download a model ─────────────────────────────────────────────────────────
echo.
echo [--] Download an AI model...
python download_model.py

echo.
echo ============================================
echo   Setup complete!  Run: start.bat
echo ============================================
echo.
pause
