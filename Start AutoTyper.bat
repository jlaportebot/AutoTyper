@echo off
cd /d "%~dp0"
where pyw >nul 2>nul && (start "" pyw main.pyw & exit /b)
where pythonw >nul 2>nul && (start "" pythonw main.pyw & exit /b)
echo Python was not found. Install it from https://www.python.org/downloads/
echo and tick "Add python.exe to PATH" during setup, then run this again.
echo.
echo Tip: download the ready-made AutoTyper.exe from the Releases page instead.
pause
