#!/bin/bash
# ═══════════════════════════════════════════════════════════════════
# TING Review — Full Installer
# Run as root on crm.tingil.co:
#   git pull && bash drive_proxy/install_review.sh
# ═══════════════════════════════════════════════════════════════════
set -e

APP_DIR="/opt/ting-review"
SERVICE="ting-review"
PORT=8001

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║     TING Review — Installer v2           ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# ── 1. Packages ───────────────────────────────────────────────────
echo "📦 Installing packages..."
apt-get update -qq
apt-get install -y -qq python3 python3-pip python3-venv curl sqlite3

# ── 2. App directory ──────────────────────────────────────────────
echo "📁 Setting up ${APP_DIR}..."
mkdir -p "${APP_DIR}/static"
cp drive_proxy/main.py          "${APP_DIR}/"
cp drive_proxy/db.py            "${APP_DIR}/"
cp drive_proxy/signing.py       "${APP_DIR}/"
cp drive_proxy/routes_team.py   "${APP_DIR}/"
cp drive_proxy/routes_client.py "${APP_DIR}/"
cp drive_proxy/requirements.txt "${APP_DIR}/"
cp drive_proxy/static/review.html "${APP_DIR}/static/"

# ── 3. Python venv ────────────────────────────────────────────────
echo "🐍 Creating venv..."
python3 -m venv "${APP_DIR}/venv"
"${APP_DIR}/venv/bin/pip" install --quiet --upgrade pip
"${APP_DIR}/venv/bin/pip" install --quiet -r "${APP_DIR}/requirements.txt"
echo "   ✅ Python packages installed"

# ── 4. .env file ─────────────────────────────────────────────────
if [ ! -f "${APP_DIR}/.env" ]; then
  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "  Creating .env — EDIT THIS FILE!"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  cat > "${APP_DIR}/.env" << 'ENV'
# TING Review — Environment Variables
GOOGLE_SERVICE_ACCOUNT_KEY=/etc/ting-drive/service-account.json
TING_DB_PATH=/opt/ting-review/ting_review.db
TING_TEAM_SECRET=CHANGE_THIS_TO_A_STRONG_SECRET
TING_SIGNING_SECRET=CHANGE_THIS_TOO_DIFFERENT_VALUE
TING_VIDEO_URL_TTL=7200
ALLOWED_ORIGINS=https://crm.tingil.co,https://ting-media-finance.web.app
ENV
  echo "   ⚠️  Edit ${APP_DIR}/.env and set strong secrets!"
  echo "   Then re-run this script or: systemctl restart ${SERVICE}"
fi

# ── 5. Systemd service ────────────────────────────────────────────
echo "⚙️  Installing systemd service..."
cat > "/etc/systemd/system/${SERVICE}.service" << SERVICE
[Unit]
Description=TING Review Server
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=${APP_DIR}
EnvironmentFile=${APP_DIR}/.env
ExecStart=${APP_DIR}/venv/bin/uvicorn main:app --host 127.0.0.1 --port ${PORT} --workers 1
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
SERVICE

systemctl daemon-reload
systemctl enable "${SERVICE}"
systemctl restart "${SERVICE}"
sleep 2

# ── 6. nginx ─────────────────────────────────────────────────────
echo "🌐 Checking nginx..."
NGINX_CONF="/etc/nginx/sites-enabled/default"
if grep -q "location /r/" "${NGINX_CONF}" 2>/dev/null; then
  echo "   ✅ nginx already has /r/ route"
else
  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "  Add these blocks to your nginx server { }"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  cat << 'NGINX'

    # TING Review — client pages + API
    location /r/ {
        proxy_pass         http://127.0.0.1:8001;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_buffering    off;
        proxy_read_timeout 300s;
    }
    location /api/ {
        proxy_pass         http://127.0.0.1:8001;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   Range $http_range;
        proxy_buffering    off;
        proxy_read_timeout 300s;
        # SSE support
        proxy_cache        off;
        proxy_set_header   Connection '';
        chunked_transfer_encoding on;
    }

NGINX
fi

# ── 7. Health check ───────────────────────────────────────────────
echo ""
echo "🩺 Health check..."
STATUS=$(curl -s http://127.0.0.1:${PORT}/api/health | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status','?'))" 2>/dev/null || echo "error")
if [ "${STATUS}" = "ok" ]; then
  echo "   ✅ TING Review is RUNNING"
  echo ""
  echo "══════════════════════════════════════════"
  echo " ✅ Done! Test:"
  echo "    curl https://crm.tingil.co/api/health"
  echo "══════════════════════════════════════════"
else
  echo "   ❌ Server not responding. Check logs:"
  echo "   journalctl -u ${SERVICE} -n 50"
fi
