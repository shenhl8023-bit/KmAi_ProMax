@echo off
setlocal EnableExtensions

REM ====================================================================
REM Stop the KmAI agent bound to the requested local port.
REM
REM Usage:
REM     stop_agent.bat               Stop the default 9095 instance
REM     stop_agent.bat 9097          Stop only the 9097 instance
REM
REM Safety:
REM   - Match python/pythonw processes running this directory's agent_server.py.
REM   - Match the requested --port argument before Stop-Process is called.
REM   - Do not kill every process whose command line merely contains agent_server.py.
REM ====================================================================

set "BASE_DIR=%~dp0"
set "AGENT_SCRIPT=%BASE_DIR%agent_server.py"
set "AGENT_PORT=%~1"
if "%AGENT_PORT%"=="" set "AGENT_PORT=9095"

for /f "delims=0123456789" %%A in ("%AGENT_PORT%") do (
  echo [ERROR] Invalid port: %AGENT_PORT%
  exit /b 1
)

echo [INFO] Stopping agent_server.py instance at port %AGENT_PORT% ...

REM ---- 1) Stop only the matching process for this script path and port ----
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$targetScript = [IO.Path]::GetFullPath('%AGENT_SCRIPT%');" ^
  "$targetPort = '%AGENT_PORT%';" ^
  "$targetPortArg = '--port\s+[''\""]?' + [regex]::Escape($targetPort) + '([''\""])?(\s|$)';" ^
  "$targetPortEqualsArg = '--port=' + [regex]::Escape($targetPort) + '(\s|$)';" ^
  "$procs = Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'python(w)?\.exe' -and $_.CommandLine -and $_.CommandLine -like '*agent_server.py*' -and ($_.CommandLine.IndexOf($targetScript, [StringComparison]::OrdinalIgnoreCase) -ge 0) -and ($_.CommandLine -match $targetPortArg -or $_.CommandLine -match $targetPortEqualsArg) };" ^
  "if (-not $procs -or $procs.Count -eq 0) { Write-Host '[INFO] No matching agent_server.py process found.'; exit 0 };" ^
  "$procs | ForEach-Object { Write-Host ('[INFO] Killing PID ' + $_.ProcessId + ' (port ' + $targetPort + ', started ' + $_.CreationDate + ')'); Stop-Process -Id $_.ProcessId -Force };" ^
  "Write-Host ('[OK] Stopped ' + $procs.Count + ' process(es).')"

REM ---- 2) Give Windows a moment to release process-owned resources ----
ping -n 2 127.0.0.1 >nul

REM ---- 3) Verify the requested port is free ----
powershell -NoProfile -Command ^
  "$c = Get-NetTCPConnection -LocalPort %AGENT_PORT% -State Listen -ErrorAction SilentlyContinue;" ^
  "if ($c) { Write-Host ('[WARN] Port ' + %AGENT_PORT% + ' still bound by PID ' + ($c.OwningProcess -join ', ')); exit 1 }" ^
  "else { Write-Host ('[OK] Port ' + %AGENT_PORT% + ' is free.') }"

endlocal
