@echo off
REM Chay thu Ha Noi: bang .csv + anh .tif ngay/dem, do thoi gian. Ket qua: C:\VNGIS_Data
chcp 65001 >nul
cd /d "%~dp0"
if exist ".venv\Scripts\activate.bat" call ".venv\Scripts\activate.bat"
set PYTHONIOENCODING=utf-8
python run_hanoi_pilot.py %*
echo.
pause
