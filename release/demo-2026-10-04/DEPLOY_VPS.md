# DEPLOY_VPS.md — triển khai landing lên VPS 103.101.162.111

**Trạng thái hiện tại (đã probe 03/10/2026):**

| Hạng mục | Giá trị | Bằng chứng |
|---|---|---|
| Port 22 (SSH) | reachable | `Test-NetConnection 103.101.162.111 -Port 22` True |
| Port 80 (HTTP) | reachable, serve site EduPortal | `curl -I http://103.101.162.111` → nginx/1.18.0 (Ubuntu) |
| Port 443 (HTTPS) | không mở | `Test-NetConnection 103.101.162.111 -Port 443` False |
| SSH key | không có trong repo/máy này | `Permission denied (publickey,password)` khi probe |
| Domain / TLS | chưa xác minh | không truy cập được để xác minh |
| Site hiện tại | landing "EduPortal" khác | nội dung HTML trả về là dự án khác |

Vì không có SSH key và VPS đang serve một landing khác, **bản demo này
KHÔNG deploy**. Khi có key, làm theo bước dưới.

## Khi có SSH key (ước lượng 60 phút)

```bash
# 0. Từ laptop, sao chép key vào VPS (KHÔNG commit key vào repo)
ssh-copy-id -i ~/.ssh/sgm_demo_ed25519.pub root@103.101.162.111

# 1. Trên VPS, tạo user không phải root + thư mục riêng
ssh root@103.101.162.111
useradd -m -s /bin/bash sgm
mkdir -p /opt/sgm/landing
chown -R sgm:sgm /opt/sgm

# 2. Từ laptop, rsync bản landing (KHÔNG gồm model/venv/node_modules)
rsync -avz --delete \
  --exclude='venv' --exclude='node_modules' --exclude='.git' \
  --exclude='*.db' --exclude='*.sqlite*' --exclude='data/' \
  ./marketing/ /opt/sgm/landing/
rsync -avz ./frontend/dist/ /opt/sgm/landing/dist/   # nếu muốn trỏ vào app luôn

# 3. Cấu hình nginx virtual host riêng trên cổng 8080
#    (KHÔNG ghi đè site EduPortal đang chạy ở cổng 80)
cat > /etc/nginx/sites-available/sgm-landing <<'EOF'
server {
    listen 8080;
    server_name _;
    root /opt/sgm/landing;
    index landing.html;
    location / { try_files $uri $uri/ =404; }
}
EOF
ln -sf /etc/nginx/sites-available/sgm-landing /etc/nginx/sites-enabled/sgm-landing
nginx -t && systemctl reload nginx

# 4. Health check từ NGOÀI máy (đã thấy IP public)
curl -I http://103.101.162.111:8080/landing.html

# 5. Rollback
rm /etc/nginx/sites-enabled/sgm-landing
systemctl reload nginx
```

## Phần này KHÔNG bao gồm

- **TLS/HTTPS**: cần domain + Let's Encrypt (certbot). Chưa có domain.
- **Auth portal / sync**: còn mở; sẽ làm sau khi có SSH.
- **Deploy backend (uvicorn)**: bản demo này chỉ serve static landing.
  Nếu muốn đẩy app, dùng systemd + nginx reverse proxy — không nằm
  trong phạm vi demo offline.

## Lý do không ghi "deployed"

Plan đợt 6 yêu cầu bằng chứng "URL/health/version từ ngoài máy" trước
khi đánh dấu deployed. Bản này chỉ probe được port 22/80, không SSH
được, không health/version từ ngoài. Trạng thái là **pending_access**,
chứ không phải deployed.