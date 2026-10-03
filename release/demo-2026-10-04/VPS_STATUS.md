# VPS_STATUS.md — Trạng thái VPS 103.101.162.111

**Probe thực hiện:** 2026-10-03 ~22:54 UTC+7, từ máy demo (192.168.1.5).

| Hạng mục | Kết quả | Phương pháp |
|---|---|---|
| Port 22 (SSH) | ✅ reachable | `Test-NetConnection 103.101.162.111 -Port 22` |
| Port 80 (HTTP) | ✅ 200 OK, `Server: nginx/1.18.0 (Ubuntu)` | `Invoke-WebRequest http://103.101.162.111` |
| Port 443 (HTTPS) | ❌ fail | `Test-NetConnection 103.101.162.111 -Port 443` |
| SSH auth (root) | ❌ `Permission denied (publickey,password)` | `ssh -o BatchMode=yes root@103.101.162.111` |
| Domain / DNS | chưa xác minh | (cần SSH để xem) |
| Site hiện tại | landing "EduPortal" (dự án khác) | nội dung `/` |
| TLS cert | n/a (port 443 đóng) | – |
| Health endpoint trên VPS | n/a (không SSH được) | – |
| Build hash trên VPS | n/a (không SSH được) | – |

## Trạng thái theo plan D9

- **D9a — SSH read-only**: ❌ chưa vào được (không có key)
- **D9b — deploy landing**: ❌ pending_access — sẽ triển khai khi có key,
  ghi rõ không ghi đè EduPortal hiện tại
- **D9c — sync**: ❌ pending_sync — chưa có hạ tầng kết nối; không nằm
  trong phạm vi demo offline

## Lệnh probe (PowerShell, có thể chạy lại)

```powershell
Test-NetConnection -ComputerName 103.101.162.111 -Port 22 -WarningAction SilentlyContinue
Test-NetConnection -ComputerName 103.101.162.111 -Port 80 -WarningAction SilentlyContinue
Test-NetConnection -ComputerName 103.101.162.111 -Port 443 -WarningAction SilentlyContinue
(Invoke-WebRequest http://103.101.162.111 -UseBasicParsing -TimeoutSec 10).Headers
ssh -o BatchMode=yes -o ConnectTimeout=10 root@103.101.162.111 "echo connected"
```

## Khi có key, xem

- `DEPLOY_VPS.md` (cùng thư mục `release/demo-2026-10-04/`) — hướng dẫn
  triển khai landing không đụng EduPortal
- `FINAL_ACCEPTANCE.md` — đánh dấu `deployed = true` chỉ khi
  URL + health + version + rollback đã kiểm từ ngoài máy

Bản demo này **không dùng VPS làm đường xử lý** — toàn bộ camera, AI,
audio chạy tại máy demo. Mất VPS hoặc WAN không làm chậm local.