# ROLLBACK_DEMO.ps1 — Quay lại bản build trước đó, giữ DB/evidence mới.
# Quy ước F1 (review e396096):
#  - Preflight TRƯỚC khi STOP: kiểm snapshot/build/config/dirty → commit restore.
#  - Nếu dirty → báo lỗi nhưng KHÔNG tắt backend hiện hành (giữ process).
#  - Rollback KHÔNG khả dụng thì giữ nguyên trạng thái, không phá runtime.

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$FromTag,    # git tag/commit trước đó
    [string]$StateFile = "",
    [switch]$NoBuild
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $root

function Info([string]$msg) { Write-Host "[ROLLBACK] $msg" -ForegroundColor Yellow }
function Ok([string]$msg) { Write-Host "[ROLLBACK] $msg" -ForegroundColor Green }
function Fail([string]$msg) { Write-Host "[ROLLBACK] $msg" -ForegroundColor Red }

if (-not $StateFile) { $StateFile = Join-Path $root "logs_demo/state/demo-backend.json" }

# 1) Preflight: verify $FromTag tồn tại VÀ có thể checkout sạch (không dirty hiện tại).
Info "Preflight: kiểm git, working tree, snapshot path…"

if (-not (Test-Path (Join-Path $root ".git"))) {
    Fail "Không phải git repo. Không thể rollback tự động."
    exit 2
}

$tagObj = git rev-parse --verify "$FromTag^{commit}" 2>$null
if ($LASTEXITCODE -ne 0) {
    Fail "Không tìm thấy commit/tag '$FromTag'."
    exit 2
}

# Snapshot thư mục trước khi đụng — chỉ file build/config/weights, KHÔNG checkout toàn bộ.
$dirty = git status --porcelain
$trackedDirty = @($dirty | Where-Object { $_ -notmatch '^\?\?' })
if ($trackedDirty.Count -gt 0) {
    Fail "Working tree có tracked file thay đổi (không stash toàn bộ):"
    $trackedDirty | ForEach-Object { Fail "  $_" }
    Fail "Giữ nguyên process hiện hành. Commit/stash thủ công trước."
    exit 2
}

# 2) Verify build $FromTag tồn tại trước khi tắt backend.
$prevDist = Join-Path $root "frontend/dist"
$hasPrevBuild = $false
git cat-file -e "$FromTag:frontend/dist/index.html" 2>$null
if ($LASTEXITCODE -eq 0) { $hasPrevBuild = $true }

if (-not $hasPrevBuild) {
    Fail "Bản $FromTag không có frontend/dist/index.html — không có bản build đã kiểm."
    Fail "Giữ nguyên process hiện hành. Build thủ công hoặc chọn tag khác."
    exit 2
}

# 3) Snapshot nhẹ các path dễ mất (DB demo + evidence).
$backupRoot = Join-Path $root "data/rollback_snapshot_$(Get-Date -Format yyyyMMdd-HHmmss)"
if (-not (Test-Path $backupRoot)) { New-Item -ItemType Directory $backupRoot | Out-Null }
foreach ($p in @("data/demo_app.db","data/demo_training.db","data/demo_snapshots")) {
    $full = Join-Path $root $p
    if (Test-Path $full) {
        Copy-Item -Path $full -Destination $backupRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}
Info "Snapshot data/ → $backupRoot"

# 4) Sau preflight pass MỚI dừng backend.
Info "Dừng backend theo state file..."
& "$PSScriptRoot/STOP_DEMO.ps1" -StateFile $StateFile
if ($LASTEXITCODE -ne 0) {
    Fail "STOP thất bại, KHÔNG checkout. Khôi phục thủ công."
    exit $LASTEXITCODE
}

# 5) Checkout chỉ frontend/dist + weights + config (không stash toàn bộ).
Info "Checkout $FromTag cho frontend/dist, app/config*.py, models/* (không đụng data/)..."
git checkout "$FromTag" -- frontend/dist app/config.py scripts/wait_for_backend.py release/demo-2026-10-04 2>$null
if ($LASTEXITCODE -ne 0) {
    Fail "git checkout thất bại. Có thể cần rollback thủ công."
    exit 4
}

# 6) (Tùy chọn) rebuild nếu bản cũ không có dist.
if (-not $NoBuild) {
    Push-Location (Join-Path $root "frontend")
    if (Test-Path dist) { Remove-Item -Recurse -Force dist }
    npm run build | Out-Host
    Pop-Location
}

Ok "Rollback xong. Chạy START_DEMO.ps1 -SkipBuild để khởi lại (giữ DB/evidence)."
exit 0