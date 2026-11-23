@echo off
rem Force-stop a running or left-over demo server and tunnel (see share.py).
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Cannot find .venv\Scripts\python.exe - follow the install steps in README.md first.
  pause
  exit /b 1
)
.venv\Scripts\python share.py stop
pause
