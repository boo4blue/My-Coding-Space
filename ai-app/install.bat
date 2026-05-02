@echo off
setlocal EnableDelayedExpansion

set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

echo.
echo ============================================
echo   ARIA -- First-Time Setup (Windows)
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
echo [OK] Python found

:: ── 2. Ollama install ──────────────────────────────────────────────────────
where ollama >nul 2>&1
if %errorlevel% neq 0 (
    echo [--] Ollama not found. Opening download page...
    echo      Download and install Ollama, then re-run this script.
    start https://ollama.com/download/windows
    echo.
    echo After installing Ollama, press any key to continue...
    pause >nul
) else (
    echo [OK] Ollama already installed
)

:: ── 3. Start Ollama ────────────────────────────────────────────────────────
curl -s http://localhost:11434/api/tags >nul 2>&1
if %errorlevel% neq 0 (
    echo [--] Starting Ollama...
    start /B ollama serve
    timeout /t 4 /nobreak >nul
)

:: ── 4. Pull a model ────────────────────────────────────────────────────────
echo.
echo Which AI model do you want to use?
echo   1) llama3.2     (~2GB -- fast, great for everyday use)
echo   2) mistral      (~4GB -- smart and fast)
echo   3) llama3.1:8b  (~5GB -- more capable)
echo   4) codellama    (~4GB -- best for coding)
echo   5) Skip (I already have a model)
echo.
set /p CHOICE="Choice [1]: "
if "%CHOICE%"=="" set CHOICE=1

if "%CHOICE%"=="1" set MODEL=llama3.2
if "%CHOICE%"=="2" set MODEL=mistral
if "%CHOICE%"=="3" set MODEL=llama3.1:8b
if "%CHOICE%"=="4" set MODEL=codellama
if "%CHOICE%"=="5" set MODEL=

if not "%MODEL%"=="" (
    echo [--] Pulling %MODEL% (this may take a while on first run^)...
    ollama pull %MODEL%
    python -c "import json; cfg=json.load(open('config.json')); cfg['default_model']='%MODEL%'; json.dump(cfg,open('config.json','w'),indent=2)"
    echo [OK] Default model set to %MODEL%
)

:: ── 5. Python venv + deps ─────────────────────────────────────────────────
echo.
echo [--] Setting up Python environment...
python -m venv .venv
call .venv\Scripts\activate.bat
pip install -q -r requirements.txt
echo [OK] Python environment ready

:: ── Done ───────────────────────────────────────────────────────────────────
echo.
echo ============================================
echo   Setup complete!
echo   Run start.bat to launch ARIA
echo ============================================
echo.
pause
