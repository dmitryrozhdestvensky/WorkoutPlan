@echo off
setlocal
cd /d "%~dp0"
echo === TenChat Collector V7 ===
if not exist ".venv\Scripts\python.exe" (
  py -m venv .venv
  if errorlevel 1 goto :failed
)
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto :failed
.venv\Scripts\python.exe -m playwright install chromium
if errorlevel 1 goto :failed
.venv\Scripts\python.exe collect_tenchat_v7.py --max-pages 250
if errorlevel 1 goto :failed
.venv\Scripts\python.exe merge_excel_v7.py
if errorlevel 1 goto :failed
echo DONE. Open fitness_trainers_merged_v7.xlsx
pause
exit /b 0
:failed
echo Error. Read the message above; progress is retained.
pause
exit /b 1
