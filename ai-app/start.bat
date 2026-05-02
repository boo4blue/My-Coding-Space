@echo off
setlocal EnableDelayedExpansion

set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

echo.
echo ============================================
echo   ARIA -- Local AI Launcher
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
for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo [OK] %%v found

:: ── Virtual environment ────────────────────────────────────────────────────
if not exist ".venv" (
    echo [--] Creating virtual environment...
    python -m venv .venv
)

call .venv\Scripts\activate.bat

:: ── Install / upgrade deps ─────────────────────────────────────────────────
echo [--] Checking dependencies...
pip install -q -r requirements.txt --upgrade
echo [OK] Dependencies ready

:: ── Ollama check / start ───────────────────────────────────────────────────
where ollama >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] Ollama found
    curl -s http://localhost:11434/api/tags >nul 2>&1
    if %errorlevel% neq 0 (
        echo [--] Starting Ollama server...
        start /B ollama serve
        timeout /t 3 /nobreak >nul
    ) else (
        echo [OK] Ollama already running
    )
) else (
    echo.
    echo [!!] Ollama not found.
    echo      Download it from: https://ollama.com/download/windows
    echo      Then run: ollama pull llama3.2
    echo      ARIA will start but AI won't work until Ollama is installed.
    echo.
)

:: ── Data directories ───────────────────────────────────────────────────────
if not exist "data\knowledge" mkdir data\knowledge
if not exist "data\uploads"   mkdir data\uploads
if not exist "data\sessions"  mkdir data\sessions

:: ── Get port from config ───────────────────────────────────────────────────
for /f %%p in ('python -c "import json; print(json.load(open('config.json')).get('port', 7860))" 2^>nul') do set PORT=%%p
if "%PORT%"=="" set PORT=7860

echo.
echo [--] Starting ARIA on http://localhost:%PORT%
echo      Press Ctrl+C to stop
echo.

python app.py
