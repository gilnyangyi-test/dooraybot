@echo off
chcp 65001 > nul
set PYTHONUTF8=1
cd /d "%~dp0"
echo Dooray 회의실 조회 작업자를 시작합니다.
"C:\Users\user\AppData\Local\Python\pythoncore-3.14-64\python.exe" worker\meeting_worker.py
pause
