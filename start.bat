@echo off
cd /d "%~dp0"
python -m pip install -q -r requirements.txt
python -m pip install -q -r requirements-desktop.txt
python -m apex %*
pause
