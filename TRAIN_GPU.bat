@echo off
REM ===== TRAIN LAI MODEL BANG GPU (tu so sanh, chi thay model khi tot hon) =====
REM Vi du:  TRAIN_GPU.bat              (train tat ca job co du lieu)
REM         TRAIN_GPU.bat --only ocr   (chi model doc ky tu bien so)
REM         TRAIN_GPU.bat --check      (chi kiem tra du lieu + GPU)
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
title School Gate Monitor - TRAIN
call venv\Scripts\activate.bat || (echo [LOI] Chay CAI_DAT.bat truoc & pause & exit /b 1)
python scripts\train_all.py %*
pause
