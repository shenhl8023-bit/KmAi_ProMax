@echo off
setlocal
cd /d "%~dp0"
python -B -m unittest discover -s tests -v
set "ROOT_TEST_EXIT=%ERRORLEVEL%"
pushd "%~dp0KmMpsMcpServer" || exit /b 1
python -B -m unittest discover -s tests -v
set "SERVER_TEST_EXIT=%ERRORLEVEL%"
popd
if not "%ROOT_TEST_EXIT%"=="0" exit /b %ROOT_TEST_EXIT%
exit /b %SERVER_TEST_EXIT%
