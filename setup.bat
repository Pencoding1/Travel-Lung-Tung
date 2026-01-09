@echo off
setlocal EnableDelayedExpansion

echo ========================================================
echo   Travel Lung Tung - Architect Setup ^& Health Check
echo ========================================================

:: 1. Performance & Path Logic
set "PROJECT_DRIVE=%~d0"
set "UV_CACHE_DIR=%PROJECT_DRIVE%\.uv_cache"
set "UV_LINK_MODE=hardlink"

:: 2. Check for uv
where uv >nul 2>nul
if %errorlevel% neq 0 (
    echo [!] uv not found. Installing...
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    echo [!] uv installed. Please RESTART this terminal and run setup.bat again.
    pause
    exit /b
)

:: 3. Hardware Detection
echo [?] Checking hardware...
powershell -Command "Get-CimInstance Win32_VideoController | Where-Object { $_.Name -match 'NVIDIA' }" >nul 2>&1
if %errorlevel% equ 0 ( set "GPU=1" & echo     - NVIDIA GPU Detected. ) else ( set "GPU=0" & echo     - No NVIDIA GPU detected. )

:: 4. Sync Environment (Mismatch Resolution)
echo [?] Syncing environment with uv.lock...
if "!GPU!"=="1" (
    uv sync
) else (
    uv sync
    uv pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
)

:: 5. SERVICE HEALTH CHECK (The Architecture Guard)
echo.
echo ========================================================
echo   Architecture Health Check
echo ========================================================

:: Check for .env file
if not exist ".env" (
    echo [ERROR] .env file missing! 
    echo         Please copy .env.example to .env and fill in credentials.
    goto end
)

echo ========================================================
echo   SETUP COMPLETE
echo ========================================================
echo To start: uv run uvicorn main:app --reload
pause