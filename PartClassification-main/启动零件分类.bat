@echo off
rem Launcher for the part-classification console service (XML in, JSON out).
rem ASCII-only and CRLF on purpose (both verified empirically, not assumed):
rem   - cmd splits a parenthesised block on multi-byte byte sequences,
rem     so non-ASCII text inside a block can become bogus commands
rem   - cmd fails to parse an LF-only .bat
rem   - the active code page is not fixed, so non-ASCII may render as mojibake
title part-classification
setlocal
cd /d "%~dp0"

rem No chcp here on purpose (measured, not assumed): `chcp 65001` makes
rem `set /p` read nothing when stdin is not a real console, and it is not
rem needed anyway - on a real console Python 3.6+ writes the JSON through
rem WriteConsoleW, and cli.py emits raw UTF-8 bytes when stdout is a file.
rem This file stays ASCII-only: cmd would garble any non-ASCII echo.

rem Prefer the py launcher: on Windows python.exe is often the Microsoft Store
rem alias, which exits silently without doing anything.
set "PYEXE=python"
where py >nul 2>&1
if not errorlevel 1 set "PYEXE=py -3"

rem A path given on the command line (or dropped onto this .bat) is used once;
rem with no argument the loop asks for one over and over.
set "XMLPATH=%~1"
rem Code handed back to a caller: the classifier's own code when it ran, 2 when
rem the typed path does not exist, 0 when the user quits without running anything.
set "LASTRC=0"

:loop
if defined XMLPATH goto have_path
echo.
echo Drag an .XML file into this window, or type its full path, then press Enter.
echo Press Enter on an empty line to quit.
set /p "XMLPATH=XML path: "

:have_path
if not defined XMLPATH goto quit
rem typing or dropping usually adds quotes; strip them all
set "XMLPATH=%XMLPATH:"=%"
if exist "%XMLPATH%" goto run

echo.
echo [FAILED] no such file: "%XMLPATH%"
set "LASTRC=2"
set "XMLPATH="
goto loop

:run
echo.
%PYEXE% -m part_classification "%XMLPATH%"
set "RC=%ERRORLEVEL%"
set "LASTRC=%RC%"
echo.
if "%RC%"=="0" goto ok

echo [FAILED] the classifier exited with code %RC%
echo.
echo Check, in order:
echo   1. Python 3.10 or newer is installed
echo   2. You ran this once in the repo root:
echo        py -3 -m pip install -e .
echo   3. The input is a KMSOFT XML; a .prt geometry file is not XML
echo      (error NOT_KMSOFT_XML means it was read but is not a KMSOFT XML)
echo.
goto next

:ok
echo [OK] classified: "%XMLPATH%"
echo.

:next
set "XMLPATH="
goto loop

:quit
endlocal & exit /b %LASTRC%
