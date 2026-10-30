@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "PY=C:\Users\24036\.workbuddy\binaries\python\envs\default\Scripts\python.exe"
if exist "%PY%" (
  "%PY%" scripts\market_admin.py
  goto :done
)

where py >nul 2>nul
if not errorlevel 1 (
  py -3 scripts\market_admin.py
  goto :done
)

python scripts\market_admin.py

:done
echo.
pause
