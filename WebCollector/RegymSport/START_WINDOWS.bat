@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto failed
.venv\Scripts\python.exe -m playwright install chromium
if errorlevel 1 goto failed
.venv\Scripts\python.exe collect_regymsport.py --show-browser
if errorlevel 1 goto failed
.venv\Scripts\python.exe merge_regymsport.py
if errorlevel 1 goto failed
echo Ready. Open fitness_trainers_merged_regymsport.xlsx
pause
exit /b 0
:failed
echo ERROR: see the message above.
pause
exit /b 1
