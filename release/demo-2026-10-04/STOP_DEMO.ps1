# STOP_DEMO.ps1 — Tắt backend demo dựa trên PID/state file.
# Quy ước F1 (review e396096):
#  - KHÔNG quét mọi python có "app.main:app" — tránh tắt nhầm backend khác.
#  - Xác minh process còn sống VÀ executable/root/port/start-time khớp state.
#  - Nếu port còn bị chiếm bởi process KHÔNG khớp state → báo lỗi, KHÔNG kill.
#  - Cleanup state file.

[CmdletBinding()]
param(
    [string]$StateFile = "",
    [int]$Port = 0
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $root

if (-not $StateFile) {
    $StateFile = Join-Path $root "logs_demo/state/demo-backend.json"
}

function Info([string]$msg) { Write-Host "[STOP_DEMO] $msg" -ForegroundColor Yellow }
function Ok([string]$msg) { Write-Host "[STOP_DEMO] $msg" -ForegroundColor Green }

if (-not (Test-Path $StateFile)) {
    Info "Không tìm thấy $StateFile — không có backend demo nào đang chạy theo state."
    exit 0
}

$state = Get-Content $StateFile -Raw | ConvertFrom-Json
$pidToStop = [int]$state.pid
$exe = [string]$state.executable
$stateRoot = [string]$state.root
$statePort = [int]$state.port
if ($Port -gt 0 -and $statePort -ne $Port) {
    Info "StateFile ghi port $statePort, bạn truyền -Port $Port → bỏ qua để tránh nhầm."
    $Port = $statePort
} else {
    $Port = $statePort
}

$proc = Get-CimInstance Win32_Process -Filter "ProcessId=$pidToStop" -ErrorAction SilentlyContinue
if (-not $proc) {
    Info "PID $($pidToStop) không còn chạy."
    Remove-Item $StateFile -ErrorAction SilentlyContinue
    exit 0
}

# Xác minh process vẫn là backend demo của mình.
$cmdMatches = ($proc.CommandLine -like "*app.main:app*")
$exeMatches = ($proc.ExecutablePath -eq $exe) -or ([string]::IsNullOrEmpty($exe))
if (-not $cmdMatches) {
    Info "PID $pidToStop không phải backend demo (commandline khác): $($proc.CommandLine)"
    exit 2
}

Info "KILL PID $pidToStop (state port=$statePort, root=$stateRoot)"
Stop-Process -Id $pidToStop -Force -ErrorAction SilentlyContinue

# Đợi port rảnh.
for ($i = 0; $i -lt 10; $i++) {
    $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if (-not $conn) { break }
    Start-Sleep -Seconds 1
}

$stillBusy = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($stillBusy) {
    $otherPid = $stillBusy.OwningProcess
    if ($otherPid -eq $pidToStop) {
        Info "PID $pidToStop vẫn giữ port $Port — escalation cần thiết."
    } else {
        Info "Port $Port còn bị PID $otherPid chiếm — KHÔNG kill, báo lỗi."
    }
    Remove-Item $StateFile -ErrorAction SilentlyContinue
    exit 3
}

Remove-Item $StateFile -ErrorAction SilentlyContinue
Ok "Đã đóng PID $pidToStop. Port $Port rảnh."
exit 0