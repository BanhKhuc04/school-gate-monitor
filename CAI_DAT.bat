@echo off
REM ===== CAI DAT 1 LAN (can mang Internet) =====
REM Tao venv, cai thu vien Python (+ torch ban CUDA neu may co GPU NVIDIA),
REM cai + build giao dien, tai san model, tao .env. Chay lai bao nhieu lan cung duoc.
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
title School Gate Monitor - CAI DAT

where python >nul 2>nul
if errorlevel 1 (
  echo [LOI] Chua cai Python 3.9+ ^(nho tick "Add python.exe to PATH"^). Xem README Buoc 1.
  goto :fail
)
where npm >nul 2>nul
if errorlevel 1 (
  echo [LOI] Chua cai Node.js 18+. Xem README Buoc 1.
  goto :fail
)

if not exist venv\Scripts\python.exe (
  echo [..] Tao moi truong ao venv...
  python -m venv venv || goto :fail
)
call venv\Scripts\activate.bat

echo [..] Cai thu vien Python ^(lan dau mat 5-15 phut^)...
python -m pip install --upgrade pip
pip install -r requirements.txt || goto :fail

REM ---- GPU: may co card NVIDIA nhung torch la ban CPU -> cai torch ban CUDA ----
where nvidia-smi >nul 2>nul
if errorlevel 1 goto :after_gpu
python -c "import torch,sys; sys.exit(0 if torch.cuda.is_available() else 1)"
if not errorlevel 1 goto :after_gpu
echo [..] May co GPU NVIDIA - cai torch ban CUDA de chay bang GPU...
for %%C in (cu126 cu128 cu124 cu121) do (
  pip install --force-reinstall --no-deps torch torchvision --index-url https://download.pytorch.org/whl/%%C && goto :after_gpu
)
echo [CANH BAO] Khong cai duoc torch ban CUDA - he thong van chay bang CPU ^(cham hon^).
:after_gpu
python -c "import torch; print('[GPU]', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'KHONG - chay CPU')"

echo [..] Cai + build giao dien...
pushd frontend
call npm install || (popd & goto :fail)
call npm run build || (popd & goto :fail)
popd

echo [..] Tai model + kiem tra he thong...
python scripts\prepare_demo.py

echo.
echo ===== XONG. Chay CHAY_DEMO.bat de bat dau. =====
pause
exit /b 0

:fail
echo.
echo ===== CAI DAT THAT BAI - doc thong bao loi ben tren =====
pause
exit /b 1
