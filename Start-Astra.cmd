@echo off
setlocal
cd /d "%~dp0"
if exist "%~dp0.venv\Scripts\python.exe" (
  "%~dp0.venv\Scripts\python.exe" "%~dp0scripts\start.py" %*
) else (
  echo Run Setup-Astra.cmd first to install the pinned local dependencies.
  pause
  exit /b 1
)
if errorlevel 1 (
  echo.
  echo ASTRA could not start. Read the error above and the README troubleshooting section.
  pause
  exit /b 1
)
exit /b 0
