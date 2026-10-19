@echo off
setlocal EnableExtensions
set "BASE_DIR=%~dp0"
call "%BASE_DIR%stop_win7.bat" %*
exit /b %ERRORLEVEL%
