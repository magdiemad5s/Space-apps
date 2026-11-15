@echo off
setlocal
echo ASTRA-SHIELD SYNTHETIC DEMO
echo Uses separate synthetic demonstration history in .local\demo. Existing records are preserved.
call "%~dp0Start-Astra.cmd" --seed-demo --db-file "%~dp0.local\demo\history_db_v2.json" %*
exit /b %errorlevel%
