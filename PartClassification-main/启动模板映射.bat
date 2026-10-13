@echo off
rem Launcher for the sample -> template mapping GUI.
rem ASCII-only and CRLF on purpose (both verified empirically, not assumed):
rem   - cmd splits a parenthesised block on multi-byte byte sequences,
rem     so non-ASCII text inside a block can become bogus commands
rem   - cmd fails to parse an LF-only .bat
rem   - the active code page is not fixed, so non-ASCII may render as mojibake
title sample-template-mapping
setlocal
cd /d "%~dp0"

rem Prefer the py launcher: on Windows python.exe is often the Microsoft Store
rem alias, which exits silently without doing anything.
set "PYEXE=python"
where py >nul 2>&1
if not errorlevel 1 set "PYEXE=py -3"

%PYEXE% -m part_classification.gui
set "RC=%ERRORLEVEL%"

if "%RC%"=="0" goto done

echo.
echo [FAILED] the GUI exited with code %RC%
echo.
echo Check, in order:
echo   1. Python 3.10 or newer is installed
echo   2. You ran this once in the repo root:
echo        py -3 -m pip install -e .
echo   3. Your Python includes tkinter (the official installer does)
echo   4. If the window showed a map error code, fix source\...\template map json
echo.
pause

:done
endlocal
