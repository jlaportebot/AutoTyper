@echo off
cd /d "%~dp0"
where pyw >nul 2>nul && (start "" pyw autotyper.pyw & exit /b)
where pythonw >nul 2>nul && (start "" pythonw autotyper.pyw & exit /b)
echo Python was not found. Install it from https://www.python.org/downloads/
echo and tick "Add python.exe to PATH" during setup, then run this again.
pause
