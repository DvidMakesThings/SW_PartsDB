#!/bin/bash
#
# DMTDB - Start Server Script
# ===========================
# Creates virtual environment, installs dependencies, and starts the server.
# Usage: ./start.sh
#

set -e  # Exit on error

# Get the directory where this script is located (works even if called from elsewhere)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "========================================"
echo "  DMTDB - Parts Database Server"
echo "========================================"
echo "  Working directory: $SCRIPT_DIR"
echo ""

# ── Create virtual environment if it doesn't exist ─────────────────────
VENV_DIR="$SCRIPT_DIR/venv"

if [ ! -d "$VENV_DIR" ]; then
    echo "[1/3] Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
    echo "      Virtual environment created at: $VENV_DIR"
else
    echo "[1/3] Virtual environment exists: $VENV_DIR"
fi

# ── Activate virtual environment ───────────────────────────────────────
echo "[2/3] Activating virtual environment..."
source "$VENV_DIR/bin/activate"

# ── Check and install requirements ─────────────────────────────────────
echo "[3/3] Checking dependencies..."

# Compare installed packages with requirements.txt
REQUIREMENTS_FILE="$SCRIPT_DIR/requirements.txt"

if [ ! -f "$REQUIREMENTS_FILE" ]; then
    echo "      ERROR: requirements.txt not found!"
    exit 1
fi

# Check if all requirements are satisfied
if pip freeze 2>/dev/null | grep -qiF flask && \
   pip freeze 2>/dev/null | grep -qiF sqlalchemy && \
   pip freeze 2>/dev/null | grep -qiF kiutils; then
    echo "      All dependencies installed."
else
    echo "      Installing/updating dependencies..."
    pip install --upgrade pip -q
    pip install -r "$REQUIREMENTS_FILE" -q
    echo "      Dependencies installed."
fi

echo ""
echo "========================================"
echo "  Starting server..."
echo "========================================"
echo ""

# ── Start the server ───────────────────────────────────────────────────
exec python3 "$SCRIPT_DIR/main.py"

