@echo off
setlocal EnableExtensions

set "BASE_DIR=%~dp0"
set "AGENT_SCRIPT=%BASE_DIR%agent_server.py"
set "AGENT_PORT=%~1"
if "%AGENT_PORT%"=="" set "AGENT_PORT=9095"
set "AGENT_HOST=127.0.0.1"
set "PYTHON_MIN_MAJOR=3"
set "PYTHON_MIN_MINOR=10"
set "PYTHON_EXE="
if "%KMAI_RUNTIME_DIR%"=="" (
  if not "%LOCALAPPDATA%"=="" (
    set "KMAI_RUNTIME_DIR=%LOCALAPPDATA%\KmAI"
  ) else (
    set "KMAI_RUNTIME_DIR=%BASE_DIR%runtime"
  )
)
set "KMAI_LOG_DIR=%KMAI_RUNTIME_DIR%\logs"
set "PYTHONDONTWRITEBYTECODE=1"
set "KMAI_HEALTH_URL=%AGENT_HOST%:%AGENT_PORT%"
set "KMAI_STARTUP_PING_URL=http://%AGENT_HOST%:%AGENT_PORT%/api/startup-ping"

REM ---- 1) Resolve Python 3.10+ runtime ----
for /f "usebackq delims=" %%i in (`powershell -NoProfile -ExecutionPolicy Bypass -File "%BASE_DIR%resolve_python_runtime.ps1" -MinMajor %PYTHON_MIN_MAJOR% -MinMinor %PYTHON_MIN_MINOR%`) do (
  set "PYTHON_EXE=%%i"
  goto :py_ok
)

echo [ERROR] Python %PYTHON_MIN_MAJOR%.%PYTHON_MIN_MINOR%+ not found.
echo         Install or bundle Python 3.10+, or set KMAI_PYTHON_EXE.
exit /b 1

:py_ok
set "KMAI_PYTHON_EXE=%PYTHON_EXE%"
set "KMAI_SKILL_PYTHON=%PYTHON_EXE%"
echo [INFO] Python: %PYTHON_EXE%
echo [INFO] Port:   %AGENT_PORT%
echo [INFO] Runtime: %KMAI_RUNTIME_DIR%

REM ---- 2) Check port availability ----
powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalPort %AGENT_PORT% -State Listen -ErrorAction SilentlyContinue) { exit 1 } else { exit 0 }" >nul 2>&1
if errorlevel 1 (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r = Invoke-RestMethod -UseBasicParsing -Uri '%KMAI_STARTUP_PING_URL%' -TimeoutSec 2; if ($r.status -eq 'ok' -and $r.app -eq 'KmAI' -and $r.kind -eq 'agent') { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
  if not errorlevel 1 (
    echo [OK] Server already running at http://%KMAI_HEALTH_URL%/
    echo      Stop with:   stop_agent.bat %AGENT_PORT%
    exit /b 0
  )
  echo [ERROR] Port %AGENT_PORT% is already in use by another process.
  echo         Try: %~nx0 9097
  exit /b 1
)

REM ---- 3) Launch hidden server process ----
echo [INFO] Launching...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$logDir = '%KMAI_LOG_DIR%'; New-Item -ItemType Directory -Force -Path $logDir | Out-Null; Start-Process -FilePath '%PYTHON_EXE%' -ArgumentList @('%AGENT_SCRIPT%','--host','%AGENT_HOST%','--port','%AGENT_PORT%') -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logDir 'agent_server.out.log') -RedirectStandardError (Join-Path $logDir 'agent_server.err.log') -PassThru | ForEach-Object { Write-Host ('[INFO] Launched PID ' + $_.Id) }" >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Failed to launch.
  exit /b 1
)

REM ---- 4) Wait until the TCP listener is ready before reporting success ----
set "KMAI_HEALTH_RETRY=0"
set "KMAI_HEALTH_MAX_RETRY=20"
echo [INFO] Waiting for listener: %KMAI_HEALTH_URL%

:wait_for_health
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $client = New-Object Net.Sockets.TcpClient; $iar = $client.BeginConnect('%AGENT_HOST%', %AGENT_PORT%, $null, $null); if (-not $iar.AsyncWaitHandle.WaitOne(2000, $false)) { $client.Close(); exit 1 }; $client.EndConnect($iar); $client.Close(); exit 0 } catch { exit 1 }" >nul 2>&1
if not errorlevel 1 goto :health_ok
set /a KMAI_HEALTH_RETRY+=1
if %KMAI_HEALTH_RETRY% GEQ %KMAI_HEALTH_MAX_RETRY% goto :health_failed
ping -n 2 127.0.0.1 >nul
goto :wait_for_health

:health_failed
echo [ERROR] Server listener did not become ready: %KMAI_HEALTH_URL%
echo         Tail logs: type "%KMAI_LOG_DIR%\agent_server.out.log"  /  type "%KMAI_LOG_DIR%\agent_server.err.log"
echo         Stop with: stop_agent.bat %AGENT_PORT%
exit /b 1

:health_ok
echo.
echo [OK] Server listening at http://%KMAI_HEALTH_URL%/
echo      Tail logs:   type "%KMAI_LOG_DIR%\agent_server.out.log"  /  type "%KMAI_LOG_DIR%\agent_server.err.log"
echo      Stop with:   stop_agent.bat %AGENT_PORT%
exit /b 0
