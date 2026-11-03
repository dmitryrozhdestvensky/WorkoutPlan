@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PORT=18743
echo ПланТренировок: http://127.0.0.1:18743
echo Оставьте это окно открытым, пока пользуетесь приложением.
python server.py
pause
