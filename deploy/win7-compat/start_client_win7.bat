@echo off
setlocal EnableExtensions
set "BASE_DIR=%~dp0"
set "KMAI_PACKAGE_ROOT=%BASE_DIR%"
if not exist "%BASE_DIR%config.ini" (
  copy /-Y "%BASE_DIR%config.example.ini" "%BASE_DIR%config.ini" >nul
  if errorlevel 1 (
    echo 无法创建 config.ini，请将 config.example.ini 复制为 config.ini，并确认安装目录可写。
    pause
    exit /b 1
  )
)
if not exist "%BASE_DIR%KmAiChatCef.exe" (
  echo KmAI 包根目录缺少 KmAiChatCef.exe。
  pause
  exit /b 1
)
start "" "%BASE_DIR%KmAiChatCef.exe" %*
exit /b %ERRORLEVEL%
