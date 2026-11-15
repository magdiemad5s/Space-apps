@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
  py -3.12 "%~dp0scripts\setup.py"
) else (
  where python >nul 2>nul
  if errorlevel 1 (
    echo Install Python 3.12 from python.org and Node.js 24 LTS, then run this setup again.
    pause
    exit /b 1
  )
  python "%~dp0scripts\setup.py"
)
if errorlevel 1 (
  echo.
  echo Setup failed. Read the error above; existing observation history was not deleted.
  pause
  exit /b 1
)
echo.
echo Setup is complete. Double-click Start-Astra.cmd to open the application.
pause
exit /b 0
