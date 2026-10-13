@echo off
setlocal EnableExtensions

if not "%~2"=="" (
  echo Usage: %~nx0 [port]
  exit /b 2
)

set "STEP_COMPARE_PORT=%~1"
if "%STEP_COMPARE_PORT%"=="" set "STEP_COMPARE_PORT=8765"
set "STEP_COMPARE_ROOT=%~dp0"
set "STEP_COMPARE_PYTHON=%STEP_COMPARE_ROOT%runtime\python\python.exe"

if not exist "%STEP_COMPARE_PYTHON%" (
  echo Embedded Python runtime is missing: "%STEP_COMPARE_PYTHON%"
  echo Re-extract the complete STEP-Compare portable ZIP and try again.
  exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%STEP_COMPARE_ROOT%scripts\start-portable.ps1" -Python "%STEP_COMPARE_PYTHON%" -Port "%STEP_COMPARE_PORT%"
exit /b %ERRORLEVEL%
