@echo off
chcp 65001 >nul
title Luma
cd /d "%~dp0"

set "PY=python"
set "PYW=pythonw"
where py >nul 2>nul && (set "PY=py -3" & set "PYW=pyw -3")

%PY% --version >nul 2>nul
if errorlevel 1 (
  echo Python was not found. Install Python 3.9+ from https://www.python.org/downloads/
  echo ^(tick "Add python.exe to PATH" during installation^)
  pause
  exit /b 1
)

if not exist ".deps-ok" (
  echo Installing Luma's libraries ^(first run only^)...
  %PY% -m pip install --upgrade -r requirements.txt
  if errorlevel 1 (
    echo Installing the libraries failed.
    pause
    exit /b 1
  )
  echo ok> ".deps-ok"
)

start "" %PYW% luma.py %*
