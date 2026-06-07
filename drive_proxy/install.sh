#!/bin/bash
# ═══════════════════════════════════════════════════════════════════
# TING Media — Drive Proxy Installer
# Run as root on the DigitalOcean VPS: bash install.sh
# ═══════════════════════════════════════════════════════════════════
set -e

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║   TING Media — Drive Proxy Installer     ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# ── 1. System packages ────────────────────────────────────────────
echo "📦 Installing system packages..."
apt-get update -qq
apt-get install -y -qq python3 python3-pip python3-venv curl

# ── 2. Create app directory ───────────────────────────────────────
echo "📁 Setting up /opt/ting-drive-proxy..."
mkdir -p /opt/ting-drive-proxy
cp server.py /opt/ting-drive-proxy/
cp requirements.txt /opt/ting-drive-proxy/

# ── 3. Python virtual environment ────────────────────────────────
echo "🐍 Creating Python venv..."
python3 -m venv /opt/ting-drive-proxy/venv
/opt/ting-drive-proxy/venv/bin/pip install --quiet --upgrade pip
/opt/ting-drive-proxy/venv/bin/pip install --quiet -r /opt/ting-drive-proxy/requirements.txt
echo "   ✅ Python packages installed"

# ── 4. Service account key directory ─────────────────────────────
mkdir -p /etc/ting-drive
chmod 700 /etc/ting-drive

if [ ! -f /etc/ting-drive/service-account.json ]; then
  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "  ACTION REQUIRED: Service Account Key"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "  Upload your service-account.json to:"
  echo "  /etc/ting-drive/service-account.json"
  echo ""
  echo "  Then run: bash /opt/ting-drive-proxy/finish-install.sh"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

  # Write finish script
  cat > /opt/ting-drive-proxy/finish-install.sh << 'FINISH'
#!/bin/bash
set -e
chmod 600 /etc/ting-drive/service-account.json
chown www-data:www-data /etc/ting-drive/service-account.json

# Register and start systemd service
cp /opt/ting-drive-proxy/ting-drive-proxy.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable ting-drive-proxy
systemctl restart ting-drive-proxy
sleep 2

# Test health
STATUS=$(curl -s http://127.0.0.1:8001/api/health | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status','?'))")
if [ "$STATUS" = "ok" ]; then
  echo ""
  echo "✅ Drive Proxy is RUNNING on port 8001"
  echo ""
else
  echo "❌ Something went wrong. Check: journalctl -u ting-drive-proxy -n 50"
fi
FINISH
  chmod +x /opt/ting-drive-proxy/finish-install.sh
  exit 0
fi

# ── 5. If key already exists, continue straight to service setup ──
bash /opt/ting-drive-proxy/finish-install.sh 2>/dev/null || true

# ── 6. nginx config ───────────────────────────────────────────────
echo ""
echo "🌐 Configuring nginx..."

NGINX_CONF="/etc/nginx/sites-available/ting-crm"
if [ -f "$NGINX_CONF" ]; then
  # Inject proxy block if not already there
  if ! grep -q "location /api/" "$NGINX_CONF"; then
    # Insert before the last closing brace of the server block
    sed -i '/^}/i\
\
    # ── Drive Video Proxy ──\
    location /api/ {\
        proxy_pass         http:\/\/127.0.0.1:8001;\
        proxy_set_header   Host $host;\
        proxy_set_header   X-Real-IP $remote_addr;\
        proxy_set_header   Range $http_range;\
        proxy_buffering    off;\
        proxy_read_timeout 300s;\
    }' "$NGINX_CONF"
    nginx -t && systemctl reload nginx
    echo "   ✅ nginx updated"
  else
    echo "   ✅ nginx already configured"
  fi
else
  echo "   ⚠️  nginx config not found at $NGINX_CONF"
  echo "   Add manually to your server block:"
  cat << 'NGINX'
    location /api/ {
        proxy_pass         http://127.0.0.1:8001;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   Range $http_range;
        proxy_buffering    off;
        proxy_read_timeout 300s;
    }
NGINX
fi

echo ""
echo "══════════════════════════════════════════"
echo " ✅ Installation complete!"
echo " Test: curl https://crm.tingil.co/api/health"
echo "══════════════════════════════════════════"
echo ""
