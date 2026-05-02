@echo off
setlocal

cd /d "%~dp0"
if exist ".venv\Scripts\activate.bat" call .venv\Scripts\activate.bat

echo.
echo ============================================
echo   Installing AI Engine (llama-cpp-python)
echo ============================================
echo.
echo This installs the pre-built version (no compiler needed).
echo.

:: Try pre-built CPU wheels first (no Visual Studio needed)
pip install llama-cpp-python --prefer-binary --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu

if %errorlevel% equ 0 (
    echo.
    echo [OK] CPU version installed successfully.
    goto :gpu_prompt
)

:: Fallback: try just --prefer-binary from PyPI
echo [--] Trying fallback install...
pip install llama-cpp-python --prefer-binary

if %errorlevel% equ 0 (
    echo [OK] Installed.
    goto :gpu_prompt
)

echo.
echo [!!] Auto-install failed.
echo      Manual fix: Open https://github.com/abetlen/llama-cpp-python/releases
echo      Download the .whl file matching your Python version (cp311 = Python 3.11)
echo      Then run: pip install path\to\file.whl
echo.
pause
exit /b 1

:gpu_prompt
echo.
set /p GPU="Do you have an NVIDIA GPU for faster responses? [y/N]: "
if /i "%GPU%"=="y" (
    echo [--] Installing CUDA version (NVIDIA GPU)...
    pip install llama-cpp-python --prefer-binary --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu121 --force-reinstall
    if %errorlevel% equ 0 (
        python -c "import json; cfg=json.load(open('config.json')); cfg['n_gpu_layers']=-1; json.dump(cfg,open('config.json','w'),indent=2)"
        echo [OK] GPU mode enabled in config.json
    )
)

echo.
echo [OK] Engine ready. Run install.bat if you haven't already.
echo.
pause
