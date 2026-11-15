@echo off
setlocal
echo ASTRA-SHIELD SYNTHETIC DEMO
echo Loads example history only when DEMO_SIM_001 is empty. Existing records are preserved.
call "%~dp0Start-Astra.cmd" --seed-demo %*
exit /b %errorlevel%
