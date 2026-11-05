@echo off
setlocal
pushd "%~dp0" || exit /b 1
set "PORT=18743"
set "PYTHONUTF8=1"
echo WorkoutPlan: http://127.0.0.1:18743
echo Keep this window open while using the app.
python server.py
popd
pause
