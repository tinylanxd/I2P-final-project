@echo off
rem Start the demo server and Cloudflare tunnel (see share.py and README.md).
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Cannot find .venv\Scripts\python.exe - follow the install steps in README.md first.
  pause
  exit /b 1
)
.venv\Scripts\python share.py
if errorlevel 1 pause
