# START_DEMO.ps1 — Khởi động bản demo School Gate Monitor 04/10/2026.
#
# Quy ước F1 (review e396096):
#  - Workspace root = parent CỦA thư mục release/demo-2026-10-04 (hai cấp trên
#    file script). Trước đây lấy 1 cấp → ra `release/` thay vì workspace root.
#  - Không cài lại venv. Nếu thiếu venv/frontend/dist/helper thì fail-fast.
#  - Khởi backend qua Start-Process -WindowStyle Hidden + PID/state file.
#  - Readiness dùng endpoint tối thiểu read-only, không bỏ auth route đầy đủ.
#  - Nạp env demo vào process backend (không copy vào .env).
#  - Tắt worker backup/training/collector khi smoke.
#  - Mở React qua HTTP backend (cùng-origin cho asset/API).

[CmdletBinding()]
param(
    [int]$Port = 8000,
    [string]$Venv = "venv",
    [string]$LogDir = "logs_demo",
    [string]$RootPath = "",
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"

# 1) Workspace root — ưu tiên RootPath nếu được truyền và xác minh.
if ($RootPath -and (Test-Path $RootPath)) {
    $root = (Resolve-Path $RootPath).Path
} else {
    # parent of parent of script dir → workspace root (script ở release/demo-2026-10-04/)
    $root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
}
Set-Location $root

function Log([string]$msg) {
    Write-Host "[START_DEMO] $msg" -ForegroundColor Cyan
}

# 2) Preflight: kiểm prerequisite tồn tại (không cài lại).
$venvPy = Join-Path $root "$Venv/Scripts/python.exe"
if (-not (Test-Path $venvPy)) {
    throw "Không tìm thấy $venvPy. Chạy setup trước (không tự cài)."
}
$frontendDist = Join-Path $root "frontend/dist/index.html"
if (-not (Test-Path $frontendDist)) {
    Log "Chưa có frontend/dist — sẽ build (ngoại lệ, không có -SkipBuild)."
    if ($SkipBuild) {
        throw "frontend/dist/index.html không tồn tại; -SkipBuild yêu cầu build sẵn."
    }
}
$waitPy = Join-Path $root "scripts/wait_for_backend.py"
if (-not (Test-Path $waitPy)) {
    throw "Không tìm thấy $waitPy. File helper phải có trước khi chạy."
}

# 3) Frontend build (nếu cần và KHÔNG skip).
if (-not $SkipBuild -and -not (Test-Path $frontendDist)) {
    Push-Location (Join-Path $root "frontend")
    npm run build | Out-Host
    Pop-Location
} else {
    Log "Đã có frontend/dist — bỏ build (dùng -SkipBuild để tắt cảnh báo)."
}

# 4) Kiểm port — báo lỗi nếu đã có process khác nghe (KHÔNG tự kill).
$portBusy = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($portBusy) {
    $existing = (Get-CimInstance Win32_Process -Filter "ProcessId=$($portBusy.OwningProcess)" -ErrorAction SilentlyContinue)
    throw ("Cởng {1} đã bị chiếm bởi PID {0} ({2}). Đổi -Port hoặc dừng process này trước." `
        -f $portBusy.OwningProcess, $Port, ($existing.Name -join ','))
}

# 5) Load env demo — set biến process-level TRƯỚC khi spawn uvicorn.
$envDemo = Join-Path $root "release/demo-2026-10-04/env.demo.example"
$envSource = $envDemo  # sử dụng file riêng cho demo (xem ghi chú dưới)
if (-not (Test-Path $envSource)) {
    # fallback env.demo.example trong repo nếu chưa có file trong release/
    $envSource = Join-Path $root "release/demo-2026-10-04/env.example"
}
if (Test-Path $envSource) {
    Get-Content $envSource | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#")) { return }
        $kv = $line -split "=", 2
        if ($kv.Length -ne 2) { return }
        $name = $kv[0].Trim()
        $value = $kv[1].Trim()
        if ($name -and -not [string]::IsNullOrEmpty($value)) {
            [System.Environment]::SetEnvironmentVariable($name, $value, "Process")
        }
    }
    Log "Đã nạp env demo từ $envSource (override process)."
} else {
    Log "Không tìm thấy env demo, dùng .env hệ thống."
}

# Worker flags — tắt cho smoke, chỉ giữ pipeline AI.
[System.Environment]::SetEnvironmentVariable("CLEANUP_ENABLED", "0", "Process")
[System.Environment]::SetEnvironmentVariable("BACKUP_ENABLED", "0", "Process")
[System.Environment]::SetEnvironmentVariable("CONTINUOUS_RECORDING_ENABLED", "0", "Process")
[System.Environment]::SetEnvironmentVariable("COLLECTOR_ENABLED", "0", "Process")
[System.Environment]::SetEnvironmentVariable("TRAINING_WORKER_ENABLED", "0", "Process")

# Force DB/paths demo riêng (không đụng dữ liệu vận hành).
[System.Environment]::SetEnvironmentVariable("APP_DB_PATH", (Join-Path $root "data/demo_app.db"), "Process")
[System.Environment]::SetEnvironmentVariable("TRAINING_DB_PATH", (Join-Path $root "data/demo_training.db"), "Process")
[System.Environment]::SetEnvironmentVariable("SNAPSHOTS_DIR", (Join-Path $root "data/demo_snapshots"), "Process")
[System.Environment]::SetEnvironmentVariable("BACKUP_DIR", (Join-Path $root "data/demo_backups"), "Process")
[System.Environment]::SetEnvironmentVariable("CONTINUOUS_RECORDING_DIR", (Join-Path $root "data/demo_recordings"), "Process")
[System.Environment]::SetEnvironmentVariable("LOG_DIR", (Join-Path $root $LogDir), "Process")
foreach ($p in @("data/demo_app.db","data/demo_training.db","data/demo_snapshots","data/demo_backups","data/demo_recordings")) {
    $full = Join-Path $root $p
    $dir = Split-Path $full -Parent
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
}

# 6) Khởi backend (WindowStyle Hidden + PID/state file).
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory $LogDir | Out-Null }
$log = Join-Path $LogDir "backend.out.log"
$err = Join-Path $LogDir "backend.err.log"
$stateDir = Join-Path $LogDir "state"
if (-not (Test-Path $stateDir)) { New-Item -ItemType Directory $stateDir | Out-Null }
$stateFile = Join-Path $stateDir "demo-backend.json"

$exe = (Resolve-Path $venvPy).Path
$argsList = @("-m","uvicorn","app.main:app","--host","127.0.0.1","--port","$Port","--no-access-log")

Log "Khởi backend trên cổng $Port, log: $log"
$proc = Start-Process -FilePath $exe `
    -ArgumentList $argsList `
    -WorkingDirectory $root `
    -RedirectStandardOutput $log `
    -RedirectStandardError $err `
    -WindowStyle Hidden `
    -PassThru

# Ghi state file (executable + root + port + start_time) để STOP/ROLLBACK dùng.
$startTime = (Get-Date).ToUniversalTime().ToString("o")
$state = @{
    pid = $proc.Id
    executable = $exe
    root = $root
    port = $Port
    args = $argsList
    start_time_utc = $startTime
    log = $log
    err = $err
    venv = $Venv
}
$state | ConvertTo-Json | Set-Content -Encoding UTF8 $stateFile

Log "Backend PID $($proc.Id); state: $stateFile"

# 7) Readiness — dùng endpoint tối thiểu (không auth) + xác minh process còn sống.
Log "Đợi backend sẵn sàng (process + port + readiness)..."
$ok = $false
for ($i = 0; $i -lt 30; $i++) {
    if ($proc.HasExited) {
        throw "Backend process đã thoát (code=$($proc.ExitCode)). Xem $err"
    }
    $listen = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($listen) {
        try {
            & $exe $waitPy --base-url "http://127.0.0.1:$Port" --retries 1 --delay 0.5
            if ($LASTEXITCODE -eq 0) { $ok = $true; break }
        } catch {}
    }
    Start-Sleep -Seconds 2
}
if (-not $ok) {
    Log "Readiness FAIL — cleanup process của mình (PID $($proc.Id))"
    try { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue } catch {}
    Remove-Item $stateFile -ErrorAction SilentlyContinue
    throw "Backend không sẵn sàng sau 60 giây."
}

# 8) Mở Guard + landing qua HTTP backend (cùng-origin cho asset + API).
Log "Mở trình duyệt qua HTTP backend"
Start-Process "http://127.0.0.1:$Port/guard" -ErrorAction SilentlyContinue | Out-Null
$landing = Join-Path $root "marketing/landing.html"
if (Test-Path $landing) {
    Start-Process "http://127.0.0.1:$Port/static/marketing/landing.html" -ErrorAction SilentlyContinue | Out-Null
}

Log "SẴN SÀNG. Tắt bằng STOP_DEMO.ps1 (PID $($proc.Id), state: $stateFile)."
exit 0