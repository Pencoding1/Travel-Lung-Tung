@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1

rem START154 - Windows demo launcher (double-click friendly).
rem The project root is derived from this file, so the script works from any
rem working directory and supports paths that contain spaces.

set "DEMO_ROOT=%~dp0"
set "DEMO_PS1=%DEMO_ROOT%scripts\native_runtime\start_demo.ps1"
set "DEMO_EXIT=0"
set "DEMO_NO_PAUSE=0"

for %%A in (%*) do (
  if /I "%%~A"=="-NoPause" set "DEMO_NO_PAUSE=1"
)

if not exist "%DEMO_PS1%" (
  echo [START154] FAILED: missing helper "%DEMO_PS1%".
  echo [START154] The demo was not started and no engine was changed.
  set "DEMO_EXIT=1"
  goto :finish
)

powershell.exe -NoProfile -File "%DEMO_PS1%" %*
set "DEMO_EXIT=%ERRORLEVEL%"

if not "%DEMO_EXIT%"=="0" (
  echo.
  echo [START154] FAILED: demo startup returned exit code %DEMO_EXIT%.
  echo [START154] Nothing was installed, downloaded or repaired. Read the message above.
)

:finish
if "%DEMO_NO_PAUSE%"=="0" pause
exit /b %DEMO_EXIT%
