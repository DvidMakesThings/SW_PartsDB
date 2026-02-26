#!/bin/bash
# ============================================================================
# DMTDB KiCad Library Sync - Linux/macOS
#
# Syncs KiCad libraries from DMTDB server and registers them in KiCad.
#
# Usage:
#   ./sync-kicad-libs.sh [OPTIONS]
#
# Options:
#   -s, --server URL      Server URL (default: http://192.168.0.25:5000)
#   -p, --path PATH       Local library path (default: ~/Documents/KiCad/DMTDB)
#   -v, --version VER     KiCad version (e.g., "8.0", auto-detected if not set)
#   -f, --force           Force download all files
#   -h, --help            Show this help
# ============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Default configuration
SERVER_URL="http://192.168.0.25:5000"
LIBS_PATH=""
KICAD_VERSION=""
FORCE=""
USER_PROVIDED_PATH=""

# Individual paths (will be fetched from server or derived from LIBS_PATH)
SYMBOLS_PATH=""
FOOTPRINTS_PATH=""
MODELS_PATH=""

# Helper functions
info() { echo -e "${CYAN}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }

show_help() {
    head -n 20 "$0" | tail -n +2 | sed 's/^# //' | sed 's/^#//'
    exit 0
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -s|--server)
            SERVER_URL="$2"
            shift 2
            ;;
        -p|--path)
            LIBS_PATH="$2"
            USER_PROVIDED_PATH="1"
            shift 2
            ;;
        -v|--version)
            KICAD_VERSION="$2"
            shift 2
            ;;
        -f|--force)
            FORCE="1"
            shift
            ;;
        -h|--help)
            show_help
            ;;
        *)
            error "Unknown option: $1"
            show_help
            ;;
    esac
done

# Remove trailing slash from server URL
SERVER_URL="${SERVER_URL%/}"

# Detect KiCad config path
get_kicad_config_path() {
    local config_base=""
    
    # macOS
    if [[ "$OSTYPE" == "darwin"* ]]; then
        config_base="$HOME/Library/Preferences/kicad"
    # Linux
    else
        config_base="$HOME/.config/kicad"
    fi
    
    if [[ ! -d "$config_base" ]]; then
        echo ""
        return
    fi
    
    # If version specified, use that
    if [[ -n "$KICAD_VERSION" ]]; then
        if [[ -d "$config_base/$KICAD_VERSION" ]]; then
            echo "$config_base/$KICAD_VERSION"
            return
        fi
    fi
    
    # Find newest version
    local newest=""
    for dir in "$config_base"/*/; do
        dirname=$(basename "$dir")
        if [[ "$dirname" =~ ^[0-9]+\.[0-9]+$ ]]; then
            newest="$dir"
        fi
    done
    
    if [[ -n "$newest" ]]; then
        echo "${newest%/}"
    else
        echo ""
    fi
}

# Test server connection
test_server() {
    if curl -s -f --connect-timeout 5 "$SERVER_URL/api/v1/libs" > /dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

# Get client configuration from server (set via Client Setup page)
get_client_config() {
    curl -s "$SERVER_URL/api/v1/libs/client" 2>/dev/null
}

# Get sync status from server
get_sync_status() {
    curl -s "$SERVER_URL/api/v1/libs/sync/status" 2>/dev/null || echo '{"needs_sync": true}'
}

# Get library list from server
get_libs() {
    curl -s "$SERVER_URL/api/v1/libs" 2>/dev/null
}

# Download file if needed
download_file() {
    local url="$1"
    local dest="$2"
    local expected_size="$3"
    
    mkdir -p "$(dirname "$dest")"
    
    local needs_download=0
    
    if [[ "$FORCE" == "1" ]]; then
        needs_download=1
    elif [[ ! -f "$dest" ]]; then
        needs_download=1
    elif [[ -n "$expected_size" ]]; then
        local current_size=$(stat -f%z "$dest" 2>/dev/null || stat -c%s "$dest" 2>/dev/null)
        if [[ "$current_size" != "$expected_size" ]]; then
            needs_download=1
        fi
    fi
    
    if [[ "$needs_download" == "1" ]]; then
        echo "  Downloading: $(basename "$dest")"
        if curl -s -f -o "$dest" "$url"; then
            return 0
        else
            warn "Failed to download: $url"
            return 1
        fi
    fi
    
    return 2  # Already up to date
}

# Parse sym-lib-table to get library names
get_existing_libs() {
    local table_file="$1"
    
    if [[ ! -f "$table_file" ]]; then
        echo ""
        return
    fi
    
    grep -oE '\(name "?[^")]+' "$table_file" 2>/dev/null | sed 's/(name "//' | sed 's/(name //' || true
}

# Update sym-lib-table with new libraries
update_sym_lib_table() {
    local kicad_config="$1"
    local symbols_path="$2"
    
    local table_file="$kicad_config/sym-lib-table"
    
    # Get existing library names
    local existing_libs=$(get_existing_libs "$table_file")
    
    # Get symbol files
    local symbol_files=$(ls "$symbols_path"/*.kicad_sym 2>/dev/null || true)
    
    if [[ -z "$symbol_files" ]]; then
        warn "No symbol files found in $symbols_path"
        return
    fi
    
    local new_count=0
    local new_entries=""
    
    for file in $symbol_files; do
        local lib_name=$(basename "$file" .kicad_sym)
        
        # Check if already exists
        if echo "$existing_libs" | grep -q "^${lib_name}$"; then
            continue
        fi
        
        info "Adding new symbol library: $lib_name"
        new_entries="$new_entries  (lib (name \"$lib_name\")(type \"KiCad\")(uri \"\${DMTDB_SYM}/$(basename "$file")\")(options \"hide\")(descr \"DMTDB - $lib_name\"))\n"
        ((new_count++)) || true
    done
    
    if [[ "$new_count" -gt 0 ]]; then
        # Backup existing file
        if [[ -f "$table_file" ]]; then
            cp "$table_file" "$table_file.bak"
            
            # Insert new entries before the closing parenthesis
            # Read the file, remove last line (closing paren), add new entries, add closing paren back
            head -n -1 "$table_file" > "$table_file.tmp"
            echo -e "$new_entries)" >> "$table_file.tmp"
            mv "$table_file.tmp" "$table_file"
        else
            # Create new table
            echo "(sym_lib_table" > "$table_file"
            echo "  (version 7)" >> "$table_file"
            echo -e "$new_entries)" >> "$table_file"
        fi
        
        success "Added $new_count new symbol libraries to sym-lib-table"
    fi
}

# Update KiCad path variables
update_kicad_paths() {
    local kicad_config="$1"
    local sym_path="$2"
    local fp_path="$3"
    local model_path="$4"
    
    local common_file="$kicad_config/kicad_common.json"
    
    if [[ -f "$common_file" ]]; then
        # Check if jq is available
        if command -v jq &> /dev/null; then
            cp "$common_file" "$common_file.bak"
            
            # Add path variables using jq
            jq --arg sym "$sym_path" --arg fp "$fp_path" --arg model "$model_path" '
                .environment.vars.DMTDB_SYM = $sym |
                .environment.vars.DMTDB_FOOTPRINT = $fp |
                .environment.vars.DMTDB_3D = $model
            ' "$common_file.bak" > "$common_file"
            
            success "Updated KiCad path variables"
        else
            warn "jq not installed - cannot auto-update kicad_common.json"
            info "Please set these path variables manually in KiCad (Preferences -> Configure Paths):"
            echo "  DMTDB_SYM = $sym_path"
            echo "  DMTDB_FOOTPRINT = $fp_path"
            echo "  DMTDB_3D = $model_path"
        fi
    else
        warn "kicad_common.json not found"
        info "Please set these path variables manually in KiCad (Preferences -> Configure Paths):"
        echo "  DMTDB_SYM = $sym_path"
        echo "  DMTDB_FOOTPRINT = $fp_path"
        echo "  DMTDB_3D = $model_path"
    fi
}

# Mark client as synced on server
mark_synced() {
    local response=$(curl -s -X POST "$SERVER_URL/api/v1/libs/client/mark-synced" 2>/dev/null)
    if [[ -n "$response" ]]; then
        info "Marked as synced on server"
    fi
}

# ============================================================================
# Main Script
# ============================================================================

echo ""
echo "======================================"
echo "  DMTDB KiCad Library Sync"
echo "======================================"
echo ""

# Check for required tools
if ! command -v curl &> /dev/null; then
    error "curl is required but not installed."
    exit 1
fi

# Test server connection
info "Connecting to server at $SERVER_URL..."
if ! test_server; then
    error "Cannot connect to server at $SERVER_URL"
    echo "Make sure the DMTDB server is running and accessible."
    exit 1
fi
success "Server connection OK"

# Fetch client configuration from server
echo ""
info "Fetching your PC's configuration from server..."
CLIENT_CONFIG=$(get_client_config)

if [[ -n "$CLIENT_CONFIG" ]]; then
    FOUND=$(echo "$CLIENT_CONFIG" | grep -o '"found":[^,}]*' | cut -d: -f2 | tr -d ' ')
    
    if [[ "$FOUND" == "true" ]]; then
        PC_NAME=$(echo "$CLIENT_CONFIG" | grep -o '"client_name":"[^"]*"' | cut -d'"' -f4)
        if [[ -n "$PC_NAME" ]]; then
            success "Found configuration for: $PC_NAME"
        else
            success "Found configuration for this PC"
        fi
        
        # Use paths from server config unless overridden by command line
        if [[ -z "$USER_PROVIDED_PATH" ]]; then
            SERVER_SYM=$(echo "$CLIENT_CONFIG" | grep -o '"path_symbols":"[^"]*"' | cut -d'"' -f4)
            SERVER_FP=$(echo "$CLIENT_CONFIG" | grep -o '"path_footprints":"[^"]*"' | cut -d'"' -f4)
            SERVER_3D=$(echo "$CLIENT_CONFIG" | grep -o '"path_3dmodels":"[^"]*"' | cut -d'"' -f4)
            
            if [[ -n "$SERVER_SYM" ]]; then
                SYMBOLS_PATH="$SERVER_SYM"
            fi
            if [[ -n "$SERVER_FP" ]]; then
                FOOTPRINTS_PATH="$SERVER_FP"
            fi
            if [[ -n "$SERVER_3D" ]]; then
                MODELS_PATH="$SERVER_3D"
            fi
        fi
    else
        warn "No configuration found for this PC on the server"
        info "Set up your paths at: $SERVER_URL/setup"
    fi
fi

# Fall back to defaults if no paths configured
if [[ -z "$SYMBOLS_PATH" ]]; then
    if [[ -z "$LIBS_PATH" ]]; then
        LIBS_PATH="$HOME/Documents/KiCad/DMTDB"
        info "Using default path: $LIBS_PATH"
    fi
    SYMBOLS_PATH="$LIBS_PATH/symbols"
    FOOTPRINTS_PATH="$LIBS_PATH/footprints"
    MODELS_PATH="$LIBS_PATH/3dmodels"
fi

info "Symbols path:    $SYMBOLS_PATH"
info "Footprints path: $FOOTPRINTS_PATH"
info "3D Models path:  $MODELS_PATH"

# Find KiCad config
KICAD_CONFIG=$(get_kicad_config_path)
if [[ -n "$KICAD_CONFIG" ]]; then
    info "KiCad config found at: $KICAD_CONFIG"
else
    warn "KiCad configuration not found. Libraries will be downloaded but not auto-registered."
fi

# Check sync status
echo ""
SYNC_STATUS=$(get_sync_status)
NEEDS_SYNC=$(echo "$SYNC_STATUS" | grep -o '"needs_sync":[^,}]*' | cut -d: -f2 | tr -d ' ')

if [[ "$FORCE" != "1" ]] && [[ "$NEEDS_SYNC" == "false" ]]; then
    success "Libraries are already in sync"
    echo "Use -f or --force to re-download all files anyway."
    exit 0
fi

if [[ "$NEEDS_SYNC" == "true" ]]; then
    info "Libraries need to be synced"
fi

# Create directories
echo ""
info "Setting up directories..."

mkdir -p "$SYMBOLS_PATH" "$FOOTPRINTS_PATH" "$MODELS_PATH"

# Get library list from server
echo ""
info "Fetching library list from server..."
LIBS_JSON=$(get_libs)

# Count downloaded files
SYM_COUNT=0
FP_COUNT=0
MODEL_COUNT=0

# Download symbols
echo ""
info "Syncing symbol libraries..."

# Parse symbols from JSON (simple grep-based parsing)
while IFS= read -r line; do
    filename=$(echo "$line" | grep -o '"filename":"[^"]*"' | cut -d'"' -f4)
    size=$(echo "$line" | grep -o '"size":[0-9]*' | cut -d: -f2)
    
    if [[ -n "$filename" ]]; then
        url="$SERVER_URL/kicad_libs/symbols/$filename"
        dest="$SYMBOLS_PATH/$filename"
        
        if download_file "$url" "$dest" "$size"; then
            ((SYM_COUNT++)) || true
        fi
    fi
done <<< "$(echo "$LIBS_JSON" | grep -o '\{"name":"[^}]*type.*kicad_sym[^}]*\}')"

# Fallback: try to extract symbol filenames differently
if [[ "$SYM_COUNT" -eq 0 ]]; then
    # Extract all .kicad_sym filenames
    for filename in $(echo "$LIBS_JSON" | grep -oE '[A-Za-z0-9_]+\.kicad_sym'); do
        url="$SERVER_URL/kicad_libs/symbols/$filename"
        dest="$SYMBOLS_PATH/$filename"
        
        if download_file "$url" "$dest" ""; then
            ((SYM_COUNT++)) || true
        fi
    done
fi

success "Symbols: $SYM_COUNT downloaded"

# Download footprints
echo ""
info "Syncing footprint libraries..."

for filename in $(echo "$LIBS_JSON" | grep -oE '[A-Za-z0-9_.-]+\.kicad_mod'); do
    url="$SERVER_URL/kicad_libs/footprints/$filename"
    dest="$FOOTPRINTS_PATH/$filename"
    
    if download_file "$url" "$dest" ""; then
        ((FP_COUNT++)) || true
    fi
done

success "Footprints: $FP_COUNT downloaded"

# Download 3D models
echo ""
info "Syncing 3D models..."

for filename in $(echo "$LIBS_JSON" | grep -oE '[A-Za-z0-9_.-]+\.(step|stp|STEP|STP)'); do
    url="$SERVER_URL/kicad_libs/3dmodels/$filename"
    dest="$MODELS_PATH/$filename"
    
    if download_file "$url" "$dest" ""; then
        ((MODEL_COUNT++)) || true
    fi
done

success "3D Models: $MODEL_COUNT downloaded"

# Update KiCad configuration
echo ""
if [[ -n "$KICAD_CONFIG" ]]; then
    info "Updating KiCad configuration..."
    
    # Update path variables
    update_kicad_paths "$KICAD_CONFIG" "$SYMBOLS_PATH" "$FOOTPRINTS_PATH" "$MODELS_PATH"
    
    # Update symbol library table
    update_sym_lib_table "$KICAD_CONFIG" "$SYMBOLS_PATH"
fi

# Mark as synced on server
mark_synced

# Done
echo ""
echo "======================================"
echo -e "${GREEN}  Sync Complete!${NC}"
echo "======================================"
echo ""
echo "Downloaded: $SYM_COUNT symbols, $FP_COUNT footprints, $MODEL_COUNT 3D models"
echo "Symbols:    $SYMBOLS_PATH"
echo "Footprints: $FOOTPRINTS_PATH"
echo "3D Models:  $MODELS_PATH"
if [[ -n "$KICAD_CONFIG" ]]; then
    echo "KiCad config: $KICAD_CONFIG"
fi
echo ""
echo -e "${YELLOW}Note: Restart KiCad if it's currently running to see the new libraries.${NC}"
echo ""
