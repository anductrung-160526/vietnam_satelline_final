@echo off
REM Cap nhat tu dong (dung cho Windows Task Scheduler).
REM Vi du: run_auto_update.bat --scope monthly   hoac   run_auto_update.bat --scope annual
chcp 65001 >nul
cd /d "%~dp0"
if exist ".venv\Scripts\activate.bat" call ".venv\Scripts\activate.bat"
set PYTHONIOENCODING=utf-8
if not exist "C:\VNGIS_Data" mkdir "C:\VNGIS_Data"
python run_auto_update.py %* >> "C:\VNGIS_Data\auto_update_console.log" 2>&1
