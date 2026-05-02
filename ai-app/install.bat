@echo off
setlocal EnableDelayedExpansion

set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

echo.
echo ============================================
echo   ARIA -- First-Time Setup (Windows)
echo   Standalone AI -- no Ollama needed
echo ============================================
echo.

:: ── 1. Python check ────────────────────────────────────────────────────────
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [!!] Python not found.
    echo      Download Python 3.11+ from https://python.org
    echo      IMPORTANT: check "Add Python to PATH" during install.
    echo.
    start https://python.org/downloads
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo [OK] %%v

:: ── 2. Virtual environment ─────────────────────────────────────────────────
if not exist ".venv" (
    echo [--] Creating virtual environment...
    python -m venv .venv
)
call .venv\Scripts\activate.bat
echo [OK] Virtual environment ready

:: ── 3. Install Python dependencies ────────────────────────────────────────
echo [--] Installing dependencies (llama-cpp-python may take a few minutes^)...
pip install -q -r requirements.txt
echo [OK] Dependencies installed

:: ── 4. GPU option ──────────────────────────────────────────────────────────
echo.
echo Do you have an NVIDIA GPU and want faster AI responses?
echo   1) No  -- use CPU (works on any machine, slower)
echo   2) Yes -- install CUDA-accelerated version (requires NVIDIA GPU + drivers)
echo.
set /p GPU_CHOICE="Choice [1]: "
if "%GPU_CHOICE%"=="" set GPU_CHOICE=1

if "%GPU_CHOICE%"=="2" (
    echo [--] Installing CUDA-accelerated llama-cpp-python...
    pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu121 --force-reinstall
    echo [OK] GPU version installed
    python -c "import json; cfg=json.load(open('config.json')); cfg['n_gpu_layers']=-1; json.dump(cfg,open('config.json','w'),indent=2)"
    echo [OK] config.json set to use GPU (n_gpu_layers: -1^)
)

:: ── 5. Download a model ────────────────────────────────────────────────────
echo.
echo [--] Now downloading an AI model...
echo      (You can skip this if you already have a .gguf file in the models/ folder^)
echo.
python download_model.py

:: ── 6. Data directories ────────────────────────────────────────────────────
if not exist "models"           mkdir models
if not exist "data\knowledge"   mkdir data\knowledge
if not exist "data\uploads"     mkdir data\uploads
if not exist "data\sessions"    mkdir data\sessions

echo.
echo ============================================
echo   Setup complete!
echo   Run start.bat to launch ARIA
echo ============================================
echo.
pause
