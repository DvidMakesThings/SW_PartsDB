#!/bin/bash
#
# DMTDB - Uninstall System Service
# =================================
# Removes the DMTDB systemd service.
# Usage: sudo ./uninstall-service.sh
#

set -e  # Exit on error

# ── Check for root privileges ──────────────────────────────────────────
if [ "$EUID" -ne 0 ]; then
    echo "ERROR: This script must be run as root (use sudo)"
    exit 1
fi

SERVICE_FILE="/etc/systemd/system/dmtdb.service"

echo "========================================"
echo "  DMTDB - Service Uninstaller"
echo "========================================"
echo ""

if [ ! -f "$SERVICE_FILE" ]; then
    echo "Service not installed (dmtdb.service not found)"
    exit 0
fi

echo "[1/4] Stopping service..."
systemctl stop dmtdb 2>/dev/null || true

echo "[2/4] Disabling service..."
systemctl disable dmtdb 2>/dev/null || true

echo "[3/4] Removing service file..."
rm -f "$SERVICE_FILE"

echo "[4/4] Reloading systemd..."
systemctl daemon-reload

echo ""
echo "========================================"
echo "  Uninstallation Complete!"
echo "========================================"
echo ""
echo "  The DMTDB service has been removed."
echo "  Your project files remain intact."
echo "  You can still run manually with: ./start.sh"
echo ""

