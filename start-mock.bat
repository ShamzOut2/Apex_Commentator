@echo off
cd /d "%~dp0"
python -m apex --mock %*
pause
