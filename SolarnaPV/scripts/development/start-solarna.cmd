@echo off
setlocal
cd /d "%~dp0\..\.."

if not exist ".venv\Scripts\python.exe" (
  echo Solarna could not find .venv\Scripts\python.exe
  echo Create the environment and install the dependencies described in README.md.
  exit /b 1
)

".venv\Scripts\python.exe" -m solarna.app %*
