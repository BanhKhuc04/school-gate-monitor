#!/usr/bin/env bash
# Deploy script cho VPS Ubuntu (103.101.162.111) — chạy backend (API+DB) + frontend
# static build. KHÔNG chạy pipeline nhận diện AI ở đây (VPS 1 vCPU/1GB không đủ) —
# camera/pipeline vẫn chạy ở máy edge tại chỗ.
#
# Cách dùng: tự SSH vào VPS rồi chạy script này (mình không tự đăng nhập hộ):
#   ssh root@103.101.162.111
#   git clone <your-repo-url> /opt/school-gate-monitor
#   cd /opt/school-gate-monitor
#   bash scripts/deploy_vps.sh
#
# ponytail: 1 script bash tuần tự, không dùng Ansible/Docker — VPS 1 vCPU/1GB
# không đáng để cõng thêm container runtime. Nâng cấp lên Docker khi thực sự
# cần multi-service/scale, chưa cần ở quy mô này.

set -euo pipefail
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOMAIN_OR_IP="103.101.162.111"

echo "==> [1/6] Cài gói hệ thống (Python, Node, Nginx)"
apt-get update -y
apt-get install -y python3-venv python3-pip nginx curl
if ! command -v node >/dev/null; then
  curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
  apt-get install -y nodejs
fi

echo "==> [2/6] Cài Python deps + tạo venv"
cd "$APP_DIR"
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "==> [3/6] Build frontend (static, không chạy dev server trên VPS)"
cd "$APP_DIR/frontend"
npm install
npm run build
cd "$APP_DIR"

echo "==> [4/6] Tạo systemd service cho backend (uvicorn, tự khởi động lại khi crash/reboot)"
cat > /etc/systemd/system/school-gate-api.service <<EOF
[Unit]
Description=School Gate Monitor API
After=network.target

[Service]
Type=simple
WorkingDirectory=${APP_DIR}
ExecStart=${APP_DIR}/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now school-gate-api

echo "==> [5/6] Cấu hình Nginx: serve frontend static + reverse-proxy API/WS/media"
cat > /etc/nginx/sites-available/school-gate-monitor <<EOF
server {
    listen 80;
    server_name ${DOMAIN_OR_IP};

    root ${APP_DIR}/frontend/dist;
    index index.html;

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
    }
    location /guard/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
    }
    location /media/ {
        proxy_pass http://127.0.0.1:8000;
    }
    location / {
        try_files \$uri /index.html;
    }
}
EOF
ln -sf /etc/nginx/sites-available/school-gate-monitor /etc/nginx/sites-enabled/school-gate-monitor
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

echo "==> [6/6] Dọn snapshot cũ tự động (cron hàng ngày, giữ 30 ngày gần nhất — 15GB SSD sẽ đầy dần nếu không dọn)"
( crontab -l 2>/dev/null | grep -v 'snapshots cleanup' ; \
  echo "0 3 * * * find ${APP_DIR}/data/snapshots -type f -mtime +30 -delete # school-gate snapshots cleanup" \
) | crontab -

echo "==> Xong. Truy cập: http://${DOMAIN_OR_IP}/"
echo "    Xem log backend:  journalctl -u school-gate-api -f"
echo "    Restart backend:  systemctl restart school-gate-api"
