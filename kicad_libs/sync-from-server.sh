#!/bin/bash
# ============================================================================
# DMTDB KiCad Library Sync via SSH
#
# Syncs libraries from server using rsync over SSH, then registers new
# symbol libraries in KiCad.
#
# Usage:
#   ./sync-from-server.sh                    # Use defaults
#   ./sync-from-server.sh user@host:/path    # Custom source
# ============================================================================

set -e

# ── Configuration ──────────────────────────────────────────────────────────
# Edit these to match your setup:

SSH_HOST="masterpi@192.168.0.25"
REMOTE_PATH="/home/masterpi/SW_PartsDB/kicad_libs"

# Local destination - where to sync files to
LOCAL_PATH="$HOME/Documents/KiCad/DMTDB"

# ───────────────────────────────────────────────────────────────────────────

# Colors
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m'

info() { echo -e "${CYAN}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }

# Allow override from command line
if [[ -n "$1" ]]; then
    if [[ "$1" == *":"* ]]; then
        SSH_HOST="${1%%:*}"
        REMOTE_PATH="${1#*:}"
    else
        LOCAL_PATH="$1"
    fi
fi

echo ""
echo "======================================"
echo "  DMTDB Library Sync (SSH)"
echo "======================================"
echo ""
info "Server: $SSH_HOST:$REMOTE_PATH"
info "Local:  $LOCAL_PATH"
echo ""

# Create local directories
mkdir -p "$LOCAL_PATH/symbols" "$LOCAL_PATH/footprints" "$LOCAL_PATH/3dmodels"

# Sync using rsync
info "Syncing symbols..."
rsync -avz --progress "$SSH_HOST:$REMOTE_PATH/symbols/" "$LOCAL_PATH/symbols/"

info "Syncing footprints..."
rsync -avz --progress "$SSH_HOST:$REMOTE_PATH/footprints/" "$LOCAL_PATH/footprints/"

info "Syncing 3D models..."
rsync -avz --progress "$SSH_HOST:$REMOTE_PATH/3dmodels/" "$LOCAL_PATH/3dmodels/"

# ── Update KiCad sym-lib-table ─────────────────────────────────────────────

# Find KiCad config
if [[ "$OSTYPE" == "darwin"* ]]; then
    KICAD_CONFIG=$(ls -d "$HOME/Library/Preferences/kicad"/*/ 2>/dev/null | tail -1)
else
    KICAD_CONFIG=$(ls -d "$HOME/.config/kicad"/*/ 2>/dev/null | tail -1)
fi

if [[ -n "$KICAD_CONFIG" ]]; then
    info "Updating KiCad config at: $KICAD_CONFIG"
    
    SYM_TABLE="$KICAD_CONFIG/sym-lib-table"
    
    # Get existing library names
    EXISTING=""
    if [[ -f "$SYM_TABLE" ]]; then
        EXISTING=$(grep -oE '\(name "[^"]+' "$SYM_TABLE" | sed 's/(name "//' || true)
    fi
    
    # Add new libraries
    NEW_COUNT=0
    for symfile in "$LOCAL_PATH/symbols"/*.kicad_sym; do
        [[ -f "$symfile" ]] || continue
        
        libname=$(basename "$symfile" .kicad_sym)
        
        if ! echo "$EXISTING" | grep -q "^${libname}$"; then
            info "Adding: $libname"
            
            # If table doesn't exist, create it
            if [[ ! -f "$SYM_TABLE" ]]; then
                echo "(sym_lib_table" > "$SYM_TABLE"
                echo "  (version 7)" >> "$SYM_TABLE"
                echo ")" >> "$SYM_TABLE"
            fi
            
            # Insert before closing paren
            sed -i.bak '$d' "$SYM_TABLE"
            echo "  (lib (name \"$libname\")(type \"KiCad\")(uri \"\${DMTDB_SYM}/$libname.kicad_sym\")(options \"hide\")(descr \"DMTDB\"))" >> "$SYM_TABLE"
            echo ")" >> "$SYM_TABLE"
            rm -f "$SYM_TABLE.bak"
            
            ((NEW_COUNT++)) || true
        fi
    done
    
    if [[ $NEW_COUNT -gt 0 ]]; then
        success "Added $NEW_COUNT new symbol libraries"
    fi
    
    # Update path variables if jq available
    COMMON_FILE="$KICAD_CONFIG/kicad_common.json"
    if [[ -f "$COMMON_FILE" ]] && command -v jq &>/dev/null; then
        cp "$COMMON_FILE" "$COMMON_FILE.bak"
        jq --arg sym "$LOCAL_PATH/symbols" \
           --arg fp "$LOCAL_PATH/footprints" \
           --arg m3d "$LOCAL_PATH/3dmodels" '
           .environment.vars.DMTDB_SYM = $sym |
           .environment.vars.DMTDB_FOOTPRINT = $fp |
           .environment.vars.DMTDB_3D = $m3d
        ' "$COMMON_FILE.bak" > "$COMMON_FILE"
        success "Updated KiCad path variables"
    else
        warn "Set these in KiCad → Preferences → Configure Paths:"
        echo "  DMTDB_SYM       = $LOCAL_PATH/symbols"
        echo "  DMTDB_FOOTPRINT = $LOCAL_PATH/footprints"
        echo "  DMTDB_3D        = $LOCAL_PATH/3dmodels"
    fi
else
    warn "KiCad config not found. Set paths manually."
fi

echo ""
success "Sync complete!"
echo -e "${YELLOW}Restart KiCad to see new libraries.${NC}"
echo ""
