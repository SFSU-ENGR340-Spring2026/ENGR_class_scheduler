@echo off
REM build_windows.bat — builds ENGR_Scheduler.exe on Windows
REM Run from the folder containing all project files.

echo Installing dependencies...
pip install pyinstaller ortools PySide6 plotly

echo Building app...
pyinstaller ENGR_Scheduler.spec

echo.
echo Done! Your app is at: dist\ENGR_Scheduler\ENGR_Scheduler.exe
echo To distribute: zip the entire dist\ENGR_Scheduler\ folder and share it.
pause
