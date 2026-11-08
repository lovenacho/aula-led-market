@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PY=C:\Users\24036\.workbuddy\binaries\python\envs\default\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
set /p VER=版本号（例如 v2.5.5）:
if "%VER%"=="" exit /b
set /p NOTES=更新说明（一行）:
echo.
"%PY%" scripts\release_app.py --version %VER% --notes "%NOTES%"
echo.
pause
