#!/bin/bash
#
# DMTDB - Install as System Service
# ==================================
# Installs DMTDB as a systemd service that starts on boot.
# Usage: sudo ./install-service.sh
#
# To uninstall:
#   sudo systemctl stop dmtdb
#   sudo systemctl disable dmtdb
#   sudo rm /etc/systemd/system/dmtdb.service
#   sudo systemctl daemon-reload
#

set -e  # Exit on error

# ── Check for root privileges ──────────────────────────────────────────
if [ "$EUID" -ne 0 ]; then
    echo "ERROR: This script must be run as root (use sudo)"
    exit 1
fi

# ── Get the directory where this script is located ─────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "========================================"
echo "  DMTDB - Service Installer"
echo "========================================"
echo "  Installation path: $SCRIPT_DIR"
echo ""

# ── Check prerequisites ────────────────────────────────────────────────
if [ ! -f "$SCRIPT_DIR/start.sh" ]; then
    echo "ERROR: start.sh not found in $SCRIPT_DIR"
    echo "       Please ensure start.sh exists before installing the service."
    exit 1
fi

if [ ! -f "$SCRIPT_DIR/main.py" ]; then
    echo "ERROR: main.py not found in $SCRIPT_DIR"
    exit 1
fi

# ── Determine the user who owns the project directory ──────────────────
# This handles the case where sudo is used - we want the original user
if [ -n "$SUDO_USER" ]; then
    SERVICE_USER="$SUDO_USER"
else
    SERVICE_USER="$(stat -c '%U' "$SCRIPT_DIR")"
fi

SERVICE_GROUP="$(id -gn "$SERVICE_USER")"

echo "  Service will run as: $SERVICE_USER:$SERVICE_GROUP"
echo ""

# ── Make start.sh executable ───────────────────────────────────────────
chmod +x "$SCRIPT_DIR/start.sh"

# ── Ensure venv exists before creating service ─────────────────────────
echo "[1/4] Setting up virtual environment..."
if [ ! -d "$SCRIPT_DIR/venv" ]; then
    sudo -u "$SERVICE_USER" bash -c "cd '$SCRIPT_DIR' && python3 -m venv venv"
fi

# Install dependencies
sudo -u "$SERVICE_USER" bash -c "cd '$SCRIPT_DIR' && source venv/bin/activate && pip install -r requirements.txt -q"
echo "      Dependencies installed."

# ── Create systemd service file ────────────────────────────────────────
SERVICE_FILE="/etc/systemd/system/dmtdb.service"

echo "[2/4] Creating systemd service file..."

cat > "$SERVICE_FILE" << EOF
[Unit]
Description=DMTDB Parts Database Server
After=network.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_GROUP
WorkingDirectory=$SCRIPT_DIR
ExecStart=$SCRIPT_DIR/venv/bin/python3 $SCRIPT_DIR/main.py
Restart=always
RestartSec=5

# Environment (optional - can be customized)
# Environment=DMTDB_HOST=0.0.0.0
# Environment=DMTDB_PORT=5000
# Environment=DMTDB_DEBUG=0

# Security hardening
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

echo "      Service file created: $SERVICE_FILE"

# ── Reload systemd and enable service ──────────────────────────────────
echo "[3/4] Enabling service..."
systemctl daemon-reload
systemctl enable dmtdb

echo "[4/4] Starting service..."
systemctl start dmtdb

# ── Show status ────────────────────────────────────────────────────────
echo ""
echo "========================================"
echo "  Installation Complete!"
echo "========================================"
echo ""
echo "  Service status:"
systemctl status dmtdb --no-pager -l || true
echo ""
echo "  Useful commands:"
echo "    sudo systemctl status dmtdb   - Check status"
echo "    sudo systemctl stop dmtdb     - Stop server"
echo "    sudo systemctl start dmtdb    - Start server"
echo "    sudo systemctl restart dmtdb  - Restart server"
echo "    sudo journalctl -u dmtdb -f   - View logs (follow)"
echo ""
echo "  Server URL: http://localhost:5000"
echo ""
