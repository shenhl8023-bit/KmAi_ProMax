@echo off
setlocal EnableExtensions
set "BASE_DIR=%~dp0"
set "PACKAGE_ROOT=%BASE_DIR:~0,-1%"
set "AGENT_PORT=%~1"
if "%AGENT_PORT%"=="" set "AGENT_PORT=9095"
set "KMAI_WIN7_COMPAT=1"
set "KMAI_PYTHON_EXE=%BASE_DIR%runtime\python.exe"
set "KMAI_SKILL_PYTHON=%BASE_DIR%runtime\python.exe"
set "KMAI_NODE_EXE=%BASE_DIR%runtime\node.exe"
if not defined KMAI_RUNTIME_DIR if defined LOCALAPPDATA set "KMAI_RUNTIME_DIR=%LOCALAPPDATA%\KmAI"
if not defined KMAI_RUNTIME_DIR if defined TEMP set "KMAI_RUNTIME_DIR=%TEMP%\KmAI"
if not defined KMAI_RUNTIME_DIR if defined TMP set "KMAI_RUNTIME_DIR=%TMP%\KmAI"
if not defined KMAI_RUNTIME_DIR if defined USERPROFILE set "KMAI_RUNTIME_DIR=%USERPROFILE%\AppData\Local\KmAI"
if not defined KMAI_RUNTIME_DIR (
  echo KMAI_RUNTIME_DIR、LOCALAPPDATA、TEMP、TMP 和 USERPROFILE 均未指向可写运行时目录。
  exit /b 1
)
rem Win7 必须使用包内的 Python 运行时启动器。
"%BASE_DIR%runtime\python.exe" "%BASE_DIR%launcher.py" stop --package-root "%PACKAGE_ROOT%" --state-dir "%KMAI_RUNTIME_DIR%" --port "%AGENT_PORT%"
exit /b %ERRORLEVEL%
