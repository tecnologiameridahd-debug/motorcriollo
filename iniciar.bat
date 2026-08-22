@echo off
cd /d "%~dp0"
title MotorCriollo
echo ================================
echo  MotorCriollo
echo ================================
echo.

python -m pip install -q -r requirements.txt
python seed.py
echo.
echo Abre: http://127.0.0.1:8789
echo.
python -m uvicorn main:app --host 127.0.0.1 --port 8789
pause
