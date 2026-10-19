@echo off
setlocal EnableExtensions
set "BASE_DIR=%~dp0"
call "%BASE_DIR%start_win7.bat" %*
exit /b %ERRORLEVEL%
