@echo off
REM ===== CHAY DEMO (1 cua so duy nhat) =====
REM Backend phuc vu luon giao dien tai http://localhost:8000 - may khac/dien thoai
REM cung mang wifi mo http://<IP-may-nay>:8000 cung xem duoc.
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
title School Gate Monitor - DEMO

if not exist venv\Scripts\python.exe (
  echo [LOI] Chua cai dat - chay CAI_DAT.bat truoc.
  pause
  exit /b 1
)
call venv\Scripts\activate.bat

if not exist frontend\dist\index.html (
  echo [..] Chua build giao dien - dang build...
  pushd frontend
  call npm install
  call npm run build
  popd
)

echo [..] Kiem tra nhanh truoc khi chay...
python scripts\prepare_demo.py --quick

echo.
echo [..] Dang khoi dong ^(nap model mat ~10-30 giay^). Trinh duyet se tu mo.
echo      Dung he thong: bam Ctrl+C trong cua so nay.
start "" cmd /c "timeout /t 20 >nul & start http://localhost:8000"
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
pause
