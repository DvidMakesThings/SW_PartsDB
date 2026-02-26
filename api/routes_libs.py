"""
api.routes_libs - /api/v1/libs/* endpoints for KiCad library management.

Handles listing and uploading symbol, footprint, and 3D model files.
"""

import hashlib
import io
import os
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from flask import request, jsonify, send_file, Response
from werkzeug.utils import secure_filename

from api import api_bp
import config


# Library directories
LIBS_DIR = config.BASE_DIR / "kicad_libs"
SYMBOLS_DIR = LIBS_DIR / "symbols"
FOOTPRINTS_DIR = LIBS_DIR / "footprints"
MODELS_DIR = LIBS_DIR / "3dmodels"

# File extension to type mapping
EXT_MAP = {
    ".kicad_sym": ("symbols", SYMBOLS_DIR),
    ".kicad_mod": ("footprints", FOOTPRINTS_DIR),
    ".step": ("3dmodels", MODELS_DIR),
    ".stp": ("3dmodels", MODELS_DIR),
    ".wrl": ("3dmodels", MODELS_DIR),
}


# ── KiCad Library Download ────────────────────────────────────────────

@api_bp.route("/libs/download")
def download_kicad_libs():
    """
    GET /api/v1/libs/download
    
    Download all KiCad library files (symbols, footprints, 3dmodels) as a ZIP.
    The ZIP structure matches the expected folder layout for KiCad.
    
    Returns a ZIP file: DMTDB_KiCad_Libraries.zip containing:
      - symbols/*.kicad_sym
      - footprints/*.kicad_mod
      - 3dmodels/*.step, *.stp, *.wrl
    """
    # Create in-memory ZIP
    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Add symbols
        if SYMBOLS_DIR.exists():
            for f in SYMBOLS_DIR.iterdir():
                if f.suffix == ".kicad_sym":
                    zf.write(f, f"symbols/{f.name}")
        
        # Add footprints
        if FOOTPRINTS_DIR.exists():
            for item in FOOTPRINTS_DIR.iterdir():
                if item.suffix == ".kicad_mod":
                    zf.write(item, f"footprints/{item.name}")
                elif item.is_dir() and item.suffix == ".pretty":
                    # Include .pretty folders with their contents
                    for mod in item.iterdir():
                        if mod.suffix == ".kicad_mod":
                            zf.write(mod, f"footprints/{item.name}/{mod.name}")
        
        # Add 3D models
        if MODELS_DIR.exists():
            for f in MODELS_DIR.iterdir():
                if f.suffix.lower() in (".step", ".stp", ".wrl"):
                    zf.write(f, f"3dmodels/{f.name}")
        
        # Add a README for setup instructions
        readme_content = """# DMTDB KiCad Libraries

Extract this ZIP to a location of your choice, then configure KiCad:

## KiCad Path Variables

In KiCad, go to Preferences → Configure Paths and add:

| Name            | Path                                    |
|-----------------|-----------------------------------------|
| DMTDB_SYM       | /path/to/extracted/symbols/             |
| DMTDB_FOOTPRINT | /path/to/extracted/footprints/          |
| DMTDB_3D        | /path/to/extracted/3dmodels/            |

Replace "/path/to/extracted/" with the actual path where you extracted this ZIP.

## Add Libraries

### Footprint Library
1. Preferences → Manage Footprint Libraries → Global Libraries
2. Click Add (+)
3. Nickname: DMTDB
4. Library Path: ${DMTDB_FOOTPRINT}

### Symbol Library (HTTP)
The HTTP library provides real-time symbol browsing from the DMTDB server.
See the main DMTDB README for HTTP library setup.

## Sync Updates

To get the latest library files, download a fresh copy from:
  http://YOUR_SERVER:5000 → "Download Libraries" button

Or run the sync manually by re-downloading and extracting.
"""
        zf.writestr("README.md", readme_content)
    
    zip_buffer.seek(0)
    
    return send_file(
        zip_buffer,
        mimetype='application/zip',
        as_attachment=True,
        download_name='DMTDB_KiCad_Libraries.zip'
    )


# ── Client Configuration & Sync ───────────────────────────────────────

def _get_client_ip() -> str:
    """Get the client's IP address from the request."""
    # Check for forwarded headers (reverse proxy)
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    if request.headers.get('X-Real-IP'):
        return request.headers.get('X-Real-IP')
    return request.remote_addr or "unknown"


def _compute_libs_hash() -> str:
    """
    Compute a hash of all library files to detect changes.
    Uses file names and modification times for speed.
    """
    hasher = hashlib.sha256()
    
    for folder, exts in [
        (SYMBOLS_DIR, [".kicad_sym"]),
        (FOOTPRINTS_DIR, [".kicad_mod"]),
        (MODELS_DIR, [".step", ".stp", ".wrl"]),
    ]:
        if folder.exists():
            files = sorted(folder.iterdir(), key=lambda f: f.name)
            for f in files:
                if f.suffix.lower() in exts:
                    stat = f.stat()
                    hasher.update(f"{f.name}:{stat.st_size}:{stat.st_mtime}".encode())
    
    return hasher.hexdigest()[:16]  # Short hash is enough


def _get_changed_files(since_hash: str) -> list[dict]:
    """
    Get list of files that may have changed since a given hash.
    Since we can't reverse the hash, we return all files with metadata.
    The client can compare against their local files.
    """
    files = []
    
    for folder, file_type, exts in [
        (SYMBOLS_DIR, "symbols", [".kicad_sym"]),
        (FOOTPRINTS_DIR, "footprints", [".kicad_mod"]),
        (MODELS_DIR, "3dmodels", [".step", ".stp", ".wrl"]),
    ]:
        if folder.exists():
            for f in folder.iterdir():
                if f.suffix.lower() in exts:
                    stat = f.stat()
                    files.append({
                        "type": file_type,
                        "name": f.name,
                        "size": stat.st_size,
                        "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                    })
    
    return files


@api_bp.route("/libs/client", methods=["GET"])
def get_client_config():
    """
    GET /api/v1/libs/client
    
    Get the configuration for the current client (identified by IP).
    If no config exists, returns a template with empty paths.
    """
    from db import get_session
    from db.models import ClientConfig
    
    client_ip = _get_client_ip()
    
    session = get_session()
    try:
        config_row = session.query(ClientConfig).filter(
            ClientConfig.client_id == client_ip
        ).first()
        
        current_hash = _compute_libs_hash()
        
        if config_row:
            needs_sync = config_row.last_sync_hash != current_hash
            return jsonify({
                "found": True,
                "client_ip": client_ip,
                "config": config_row.to_dict(),
                "current_libs_hash": current_hash,
                "needs_sync": needs_sync,
            })
        else:
            return jsonify({
                "found": False,
                "client_ip": client_ip,
                "config": {
                    "client_id": client_ip,
                    "client_name": "",
                    "path_symbols": "",
                    "path_footprints": "",
                    "path_3dmodels": "",
                    "server_url": request.host_url.rstrip('/'),
                    "last_sync": None,
                    "last_sync_hash": "",
                },
                "current_libs_hash": current_hash,
                "needs_sync": True,
            })
    finally:
        session.close()


@api_bp.route("/libs/client", methods=["POST"])
def save_client_config():
    """
    POST /api/v1/libs/client
    
    Save/update configuration for the current client.
    
    JSON body:
      - client_name: (optional) Friendly name for this PC
      - path_symbols: Local path to symbols folder
      - path_footprints: Local path to footprints folder
      - path_3dmodels: Local path to 3D models folder
    """
    from db import get_session
    from db.models import ClientConfig
    
    client_ip = _get_client_ip()
    data = request.get_json() or {}
    
    session = get_session()
    try:
        config_row = session.query(ClientConfig).filter(
            ClientConfig.client_id == client_ip
        ).first()
        
        if not config_row:
            config_row = ClientConfig(client_id=client_ip)
            session.add(config_row)
        
        # Update fields
        if "client_name" in data:
            config_row.client_name = data["client_name"]
        if "path_symbols" in data:
            config_row.path_symbols = data["path_symbols"]
        if "path_footprints" in data:
            config_row.path_footprints = data["path_footprints"]
        if "path_3dmodels" in data:
            config_row.path_3dmodels = data["path_3dmodels"]
        if "server_url" in data:
            config_row.server_url = data["server_url"]
        
        session.commit()
        
        return jsonify({
            "success": True,
            "client_ip": client_ip,
            "config": config_row.to_dict(),
        })
    finally:
        session.close()


@api_bp.route("/libs/client/mark-synced", methods=["POST"])
def mark_client_synced():
    """
    POST /api/v1/libs/client/mark-synced
    
    Mark the current client as synced with the current library state.
    Call this after successfully downloading/syncing library files.
    """
    from db import get_session
    from db.models import ClientConfig
    
    client_ip = _get_client_ip()
    current_hash = _compute_libs_hash()
    
    session = get_session()
    try:
        config_row = session.query(ClientConfig).filter(
            ClientConfig.client_id == client_ip
        ).first()
        
        if not config_row:
            config_row = ClientConfig(client_id=client_ip)
            session.add(config_row)
        
        config_row.last_sync = datetime.now(timezone.utc)
        config_row.last_sync_hash = current_hash
        
        session.commit()
        
        return jsonify({
            "success": True,
            "client_ip": client_ip,
            "synced_at": config_row.last_sync.isoformat(),
            "libs_hash": current_hash,
        })
    finally:
        session.close()


@api_bp.route("/libs/sync/status")
def sync_status():
    """
    GET /api/v1/libs/sync/status
    
    Check if the current client needs to sync library files.
    Returns sync status and list of all library files with metadata.
    """
    from db import get_session
    from db.models import ClientConfig
    
    client_ip = _get_client_ip()
    current_hash = _compute_libs_hash()
    
    session = get_session()
    try:
        config_row = session.query(ClientConfig).filter(
            ClientConfig.client_id == client_ip
        ).first()
        
        if config_row and config_row.last_sync_hash == current_hash:
            return jsonify({
                "needs_sync": False,
                "client_ip": client_ip,
                "last_sync": config_row.last_sync.isoformat() if config_row.last_sync else None,
                "current_hash": current_hash,
                "files": [],  # No need to list files if in sync
            })
        else:
            return jsonify({
                "needs_sync": True,
                "client_ip": client_ip,
                "last_sync": config_row.last_sync.isoformat() if config_row and config_row.last_sync else None,
                "last_hash": config_row.last_sync_hash if config_row else None,
                "current_hash": current_hash,
                "files": _get_changed_files(config_row.last_sync_hash if config_row else ""),
            })
    finally:
        session.close()


@api_bp.route("/libs/clients")
def list_clients():
    """
    GET /api/v1/libs/clients
    
    List all registered client configurations.
    Useful for admin overview of which PCs have synced.
    """
    from db import get_session
    from db.models import ClientConfig
    
    current_hash = _compute_libs_hash()
    
    session = get_session()
    try:
        clients = session.query(ClientConfig).order_by(ClientConfig.client_id).all()
        return jsonify({
            "current_libs_hash": current_hash,
            "clients": [
                {
                    **c.to_dict(),
                    "needs_sync": c.last_sync_hash != current_hash,
                }
                for c in clients
            ],
        })
    finally:
        session.close()


@api_bp.route("/libs/sync-script")
def generate_sync_script():
    """
    GET /api/v1/libs/sync-script?platform=windows|unix
    
    Generate a personalized sync script with the client's configured paths.
    Downloads as a .ps1 (Windows) or .sh (Unix) file.
    """
    from db import get_session
    from db.models import ClientConfig
    
    platform = request.args.get("platform", "windows").lower()
    client_ip = _get_client_ip()
    server_url = request.host_url.rstrip('/')
    
    # Get client config
    session = get_session()
    try:
        config_row = session.query(ClientConfig).filter(
            ClientConfig.client_id == client_ip
        ).first()
        
        if config_row:
            sym_path = config_row.path_symbols or ""
            fp_path = config_row.path_footprints or ""
            m3d_path = config_row.path_3dmodels or ""
        else:
            sym_path = ""
            fp_path = ""
            m3d_path = ""
    finally:
        session.close()
    
    if platform == "windows":
        script = _generate_windows_sync_script(server_url, sym_path, fp_path, m3d_path)
        filename = "sync-dmtdb.ps1"
        mimetype = "text/plain"
    else:
        script = _generate_unix_sync_script(server_url, sym_path, fp_path, m3d_path)
        filename = "sync-dmtdb.sh"
        mimetype = "text/x-shellscript"
    
    return Response(
        script,
        mimetype=mimetype,
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


def _generate_windows_sync_script(server_url: str, sym_path: str, fp_path: str, m3d_path: str) -> str:
    """Generate PowerShell sync script."""
    
    # Use defaults if paths not configured
    if not sym_path:
        sym_path = "$env:USERPROFILE\\Documents\\KiCad\\DMTDB\\symbols"
    if not fp_path:
        fp_path = "$env:USERPROFILE\\Documents\\KiCad\\DMTDB\\footprints"
    if not m3d_path:
        m3d_path = "$env:USERPROFILE\\Documents\\KiCad\\DMTDB\\3dmodels"
    
    return f'''#Requires -Version 5.1
<#
.SYNOPSIS
    DMTDB KiCad Library Sync Script
    Generated for your PC with your configured paths.
    
.DESCRIPTION
    Downloads library files from DMTDB server and configures KiCad.
    Run this script whenever you want to sync the latest libraries.
    
.EXAMPLE
    .\\sync-dmtdb.ps1
#>

$ErrorActionPreference = "Stop"

# ============================================================================
# Configuration (from your DMTDB Client Setup)
# ============================================================================
$ServerUrl = "{server_url}"
$SymbolsPath = "{sym_path}"
$FootprintsPath = "{fp_path}"
$ModelsPath = "{m3d_path}"
# ============================================================================

function Write-Info {{ param([string]$m) Write-Host "[INFO] $m" -ForegroundColor Cyan }}
function Write-OK {{ param([string]$m) Write-Host "[OK] $m" -ForegroundColor Green }}
function Write-Warn {{ param([string]$m) Write-Host "[WARN] $m" -ForegroundColor Yellow }}

Write-Host ""
Write-Host "======================================" -ForegroundColor Cyan
Write-Host "  DMTDB KiCad Library Sync" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""

# Test server
Write-Info "Connecting to $ServerUrl..."
try {{
    $null = Invoke-RestMethod -Uri "$ServerUrl/api/v1/libs" -TimeoutSec 5
    Write-OK "Server connected"
}} catch {{
    Write-Host "[ERROR] Cannot connect to server" -ForegroundColor Red
    exit 1
}}

# Create directories
Write-Info "Creating directories..."
foreach ($dir in @($SymbolsPath, $FootprintsPath, $ModelsPath)) {{
    if (-not (Test-Path $dir)) {{
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        Write-Info "Created: $dir"
    }}
}}

# Get library list
Write-Info "Fetching library list..."
$libs = Invoke-RestMethod -Uri "$ServerUrl/api/v1/libs"

# Download symbols
Write-Info "Downloading symbols..."
$symCount = 0
foreach ($sym in $libs.symbols) {{
    $dest = Join-Path $SymbolsPath $sym.filename
    $url = "$ServerUrl/kicad_libs/symbols/$($sym.filename)"
    
    $needsDownload = (-not (Test-Path $dest)) -or ((Get-Item $dest).Length -ne $sym.size)
    
    if ($needsDownload) {{
        Write-Host "  $($sym.filename)" -ForegroundColor Gray
        Invoke-WebRequest -Uri $url -OutFile $dest -UseBasicParsing
        $symCount++
    }}
}}
Write-OK "Symbols: $symCount new/updated"

# Download footprints
Write-Info "Downloading footprints..."
$fpCount = 0
foreach ($fp in $libs.footprints) {{
    $dest = Join-Path $FootprintsPath $fp.filename
    $url = "$ServerUrl/kicad_libs/footprints/$($fp.filename)"
    
    $needsDownload = (-not (Test-Path $dest)) -or ((Get-Item $dest).Length -ne $fp.size)
    
    if ($needsDownload) {{
        Write-Host "  $($fp.filename)" -ForegroundColor Gray
        Invoke-WebRequest -Uri $url -OutFile $dest -UseBasicParsing
        $fpCount++
    }}
}}
Write-OK "Footprints: $fpCount new/updated"

# Download 3D models
Write-Info "Downloading 3D models..."
$m3dCount = 0
foreach ($model in $libs.'3dmodels') {{
    $dest = Join-Path $ModelsPath $model.filename
    $url = "$ServerUrl/kicad_libs/3dmodels/$($model.filename)"
    
    $needsDownload = (-not (Test-Path $dest)) -or ((Get-Item $dest).Length -ne $model.size)
    
    if ($needsDownload) {{
        Write-Host "  $($model.filename)" -ForegroundColor Gray
        Invoke-WebRequest -Uri $url -OutFile $dest -UseBasicParsing
        $m3dCount++
    }}
}}
Write-OK "3D Models: $m3dCount new/updated"

# ── Configure KiCad ────────────────────────────────────────────────────────

$kicadBase = Join-Path $env:APPDATA "kicad"
$kicadConfig = $null

if (Test-Path $kicadBase) {{
    $versions = Get-ChildItem -Path $kicadBase -Directory | 
        Where-Object {{ $_.Name -match '^\\d+\\.\\d+$' }} |
        Sort-Object {{ [version]$_.Name }} -Descending
    
    if ($versions.Count -gt 0) {{
        $kicadConfig = $versions[0].FullName
    }}
}}

if ($kicadConfig) {{
    Write-Info "Configuring KiCad at: $kicadConfig"
    
    # Update path variables in kicad_common.json
    $commonFile = Join-Path $kicadConfig "kicad_common.json"
    if (Test-Path $commonFile) {{
        $json = Get-Content $commonFile -Raw | ConvertFrom-Json
        
        if (-not $json.environment) {{
            $json | Add-Member -NotePropertyName "environment" -NotePropertyValue @{{}} -Force
        }}
        if (-not $json.environment.vars) {{
            $json.environment | Add-Member -NotePropertyName "vars" -NotePropertyValue @{{}} -Force
        }}
        
        $json.environment.vars | Add-Member -NotePropertyName "DMTDB_SYM" -NotePropertyValue ($SymbolsPath -replace '\\\\', '/') -Force
        $json.environment.vars | Add-Member -NotePropertyName "DMTDB_FOOTPRINT" -NotePropertyValue ($FootprintsPath -replace '\\\\', '/') -Force
        $json.environment.vars | Add-Member -NotePropertyName "DMTDB_3D" -NotePropertyValue ($ModelsPath -replace '\\\\', '/') -Force
        
        $json | ConvertTo-Json -Depth 10 | Out-File $commonFile -Encoding utf8
        Write-OK "Updated KiCad path variables"
    }}
    
    # Update sym-lib-table
    $symTable = Join-Path $kicadConfig "sym-lib-table"
    
    $existing = @()
    if (Test-Path $symTable) {{
        $content = Get-Content $symTable -Raw
        $matches = [regex]::Matches($content, '\\(name\\s+"([^"]+)"\\)')
        $existing = $matches | ForEach-Object {{ $_.Groups[1].Value }}
    }}
    
    $newLibs = 0
    $symFiles = Get-ChildItem -Path $SymbolsPath -Filter "*.kicad_sym" -ErrorAction SilentlyContinue
    
    foreach ($file in $symFiles) {{
        $libName = $file.BaseName
        
        if ($libName -notin $existing) {{
            Write-Info "Adding symbol library: $libName"
            
            if (-not (Test-Path $symTable)) {{
                "(sym_lib_table`n  (version 7)`n)" | Out-File $symTable -Encoding utf8
            }}
            
            $lines = Get-Content $symTable
            $lines = $lines[0..($lines.Count - 2)]
            $lines += "  (lib (name `"$libName`")(type `"KiCad`")(uri `"`${{DMTDB_SYM}}/$($file.Name)`")(options `"hide`")(descr `"DMTDB`"))"
            $lines += ")"
            $lines | Out-File $symTable -Encoding utf8
            
            $newLibs++
        }}
    }}
    
    if ($newLibs -gt 0) {{
        Write-OK "Added $newLibs new symbol libraries (hidden by default)"
    }}
}} else {{
    Write-Warn "KiCad config not found. Please set paths manually:"
    Write-Host "  DMTDB_SYM       = $($SymbolsPath -replace '\\\\', '/')"
    Write-Host "  DMTDB_FOOTPRINT = $($FootprintsPath -replace '\\\\', '/')"
    Write-Host "  DMTDB_3D        = $($ModelsPath -replace '\\\\', '/')"
}}

# Mark as synced on server
try {{
    $null = Invoke-RestMethod -Uri "$ServerUrl/api/v1/libs/client/mark-synced" -Method Post
    Write-Info "Marked as synced on server"
}} catch {{
    Write-Warn "Could not mark sync status"
}}

Write-Host ""
Write-Host "======================================" -ForegroundColor Green
Write-Host "  Sync Complete!" -ForegroundColor Green
Write-Host "======================================" -ForegroundColor Green
Write-Host ""
Write-Host "Downloaded: $symCount symbols, $fpCount footprints, $m3dCount 3D models"
Write-Host ""
Write-Host "Restart KiCad to see the new libraries." -ForegroundColor Yellow
Write-Host ""
'''


def _generate_unix_sync_script(server_url: str, sym_path: str, fp_path: str, m3d_path: str) -> str:
    """Generate Bash sync script."""
    
    # Use defaults if paths not configured
    if not sym_path:
        sym_path = "$HOME/Documents/KiCad/DMTDB/symbols"
    if not fp_path:
        fp_path = "$HOME/Documents/KiCad/DMTDB/footprints"
    if not m3d_path:
        m3d_path = "$HOME/Documents/KiCad/DMTDB/3dmodels"
    
    return f'''#!/bin/bash
# ============================================================================
# DMTDB KiCad Library Sync Script
# Generated for your PC with your configured paths.
#
# Run this script whenever you want to sync the latest libraries.
# Usage: chmod +x sync-dmtdb.sh && ./sync-dmtdb.sh
# ============================================================================

set -e

# Configuration (from your DMTDB Client Setup)
SERVER_URL="{server_url}"
SYMBOLS_PATH="{sym_path}"
FOOTPRINTS_PATH="{fp_path}"
MODELS_PATH="{m3d_path}"

# Colors
GREEN='\\033[0;32m'
CYAN='\\033[0;36m'
YELLOW='\\033[1;33m'
NC='\\033[0m'

info() {{ echo -e "${{CYAN}}[INFO]${{NC}} $1"; }}
ok() {{ echo -e "${{GREEN}}[OK]${{NC}} $1"; }}
warn() {{ echo -e "${{YELLOW}}[WARN]${{NC}} $1"; }}

echo ""
echo "======================================"
echo "  DMTDB KiCad Library Sync"
echo "======================================"
echo ""

# Test server
info "Connecting to $SERVER_URL..."
if ! curl -sf "$SERVER_URL/api/v1/libs" > /dev/null 2>&1; then
    echo -e "\\033[0;31m[ERROR]\\033[0m Cannot connect to server"
    exit 1
fi
ok "Server connected"

# Create directories
info "Creating directories..."
mkdir -p "$SYMBOLS_PATH" "$FOOTPRINTS_PATH" "$MODELS_PATH"

# Get library list
info "Fetching library list..."
LIBS_JSON=$(curl -s "$SERVER_URL/api/v1/libs")

# Download symbols
info "Downloading symbols..."
SYM_COUNT=0
for filename in $(echo "$LIBS_JSON" | grep -oE '"filename":"[^"]+\\.kicad_sym"' | cut -d'"' -f4); do
    dest="$SYMBOLS_PATH/$filename"
    url="$SERVER_URL/kicad_libs/symbols/$filename"
    
    if [[ ! -f "$dest" ]]; then
        echo "  $filename"
        curl -sf -o "$dest" "$url"
        ((SYM_COUNT++)) || true
    fi
done
ok "Symbols: $SYM_COUNT new/updated"

# Download footprints
info "Downloading footprints..."
FP_COUNT=0
for filename in $(echo "$LIBS_JSON" | grep -oE '"filename":"[^"]+\\.kicad_mod"' | cut -d'"' -f4); do
    dest="$FOOTPRINTS_PATH/$filename"
    url="$SERVER_URL/kicad_libs/footprints/$filename"
    
    if [[ ! -f "$dest" ]]; then
        echo "  $filename"
        curl -sf -o "$dest" "$url"
        ((FP_COUNT++)) || true
    fi
done
ok "Footprints: $FP_COUNT new/updated"

# Download 3D models
info "Downloading 3D models..."
M3D_COUNT=0
for filename in $(echo "$LIBS_JSON" | grep -oE '"filename":"[^"]+\\.(step|stp|STEP|STP)"' | cut -d'"' -f4); do
    dest="$MODELS_PATH/$filename"
    url="$SERVER_URL/kicad_libs/3dmodels/$filename"
    
    if [[ ! -f "$dest" ]]; then
        echo "  $filename"
        curl -sf -o "$dest" "$url"
        ((M3D_COUNT++)) || true
    fi
done
ok "3D Models: $M3D_COUNT new/updated"

# ── Configure KiCad ────────────────────────────────────────────────────────

# Find KiCad config
if [[ "$OSTYPE" == "darwin"* ]]; then
    KICAD_CONFIG=$(ls -d "$HOME/Library/Preferences/kicad"/*/ 2>/dev/null | tail -1)
else
    KICAD_CONFIG=$(ls -d "$HOME/.config/kicad"/*/ 2>/dev/null | tail -1)
fi

if [[ -n "$KICAD_CONFIG" ]]; then
    info "Configuring KiCad at: $KICAD_CONFIG"
    
    # Update path variables
    COMMON_FILE="${{KICAD_CONFIG}}kicad_common.json"
    if [[ -f "$COMMON_FILE" ]] && command -v jq &>/dev/null; then
        cp "$COMMON_FILE" "$COMMON_FILE.bak"
        jq --arg sym "$SYMBOLS_PATH" --arg fp "$FOOTPRINTS_PATH" --arg m3d "$MODELS_PATH" '
           .environment.vars.DMTDB_SYM = $sym |
           .environment.vars.DMTDB_FOOTPRINT = $fp |
           .environment.vars.DMTDB_3D = $m3d
        ' "$COMMON_FILE.bak" > "$COMMON_FILE"
        ok "Updated KiCad path variables"
    else
        warn "Install jq for automatic path variable setup, or set manually:"
        echo "  DMTDB_SYM       = $SYMBOLS_PATH"
        echo "  DMTDB_FOOTPRINT = $FOOTPRINTS_PATH"
        echo "  DMTDB_3D        = $MODELS_PATH"
    fi
    
    # Update sym-lib-table
    SYM_TABLE="${{KICAD_CONFIG}}sym-lib-table"
    
    EXISTING=""
    if [[ -f "$SYM_TABLE" ]]; then
        EXISTING=$(grep -oE '\\(name "[^"]+' "$SYM_TABLE" | sed 's/(name "//' || true)
    fi
    
    NEW_LIBS=0
    for symfile in "$SYMBOLS_PATH"/*.kicad_sym; do
        [[ -f "$symfile" ]] || continue
        
        libname=$(basename "$symfile" .kicad_sym)
        
        if ! echo "$EXISTING" | grep -q "^${{libname}}$"; then
            info "Adding symbol library: $libname"
            
            if [[ ! -f "$SYM_TABLE" ]]; then
                echo "(sym_lib_table" > "$SYM_TABLE"
                echo "  (version 7)" >> "$SYM_TABLE"
                echo ")" >> "$SYM_TABLE"
            fi
            
            sed -i.bak '$ d' "$SYM_TABLE"
            echo "  (lib (name \\"$libname\\")(type \\"KiCad\\")(uri \\"\\${{DMTDB_SYM}}/$libname.kicad_sym\\")(options \\"hide\\")(descr \\"DMTDB\\"))" >> "$SYM_TABLE"
            echo ")" >> "$SYM_TABLE"
            rm -f "$SYM_TABLE.bak"
            
            ((NEW_LIBS++)) || true
        fi
    done
    
    if [[ $NEW_LIBS -gt 0 ]]; then
        ok "Added $NEW_LIBS new symbol libraries (hidden by default)"
    fi
else
    warn "KiCad config not found. Please set paths manually."
fi

# Mark as synced
curl -sf -X POST "$SERVER_URL/api/v1/libs/client/mark-synced" > /dev/null 2>&1 || true
info "Marked as synced on server"

echo ""
echo "======================================"
echo -e "${{GREEN}}  Sync Complete!${{NC}}"
echo "======================================"
echo ""
echo "Downloaded: $SYM_COUNT symbols, $FP_COUNT footprints, $M3D_COUNT 3D models"
echo ""
echo -e "${{YELLOW}}Restart KiCad to see the new libraries.${{NC}}"
echo ""
'''


def _generate_symbol_value(part_data: dict, tt: str = "", ff: str = "") -> str:
    """
    Generate a symbol Value property from part database fields.
    
    Naming conventions:
    - Capacitors (TT=01, FF=01): {Capacitance} {Voltage - Rated} {Package / Case}
    - Resistors  (TT=01, FF=02): {Resistance} {Tolerance} {Package / Case}
    - Inductors  (TT=01, FF=03): {Inductance} {Current Rating (Amps)}
    - All others: MPN
    """
    # Get TT/FF from part_data if not provided
    if not tt:
        tt = part_data.get("tt", "")
    if not ff:
        ff = part_data.get("ff", "")
    
    package = part_data.get("Package / Case", "").strip()
    
    # Passives domain
    if tt == "01":
        if ff == "01":  # Capacitors
            capacitance = part_data.get("Capacitance", "").strip()
            voltage = part_data.get("Voltage - Rated", "").strip()
            if capacitance:
                parts = [capacitance, voltage, package]
                return " ".join(p for p in parts if p)
        
        elif ff == "02":  # Resistors
            resistance = part_data.get("Resistance", "").strip()
            tolerance = part_data.get("Tolerance", "").strip()
            if resistance:
                parts = [resistance, tolerance, package]
                return " ".join(p for p in parts if p)
        
        elif ff == "03":  # Inductors
            inductance = part_data.get("Inductance", "").strip()
            current = part_data.get("Current Rating (Amps)", "").strip()
            if inductance:
                parts = [inductance, current]
                return " ".join(p for p in parts if p)
    
    # All others: use MPN
    return part_data.get("mpn", "") or part_data.get("MPN", "") or ""


@api_bp.route("/libs")
def list_libs():
    """
    GET /api/v1/libs
    
    List all KiCad library files organized by type.
    """
    result = {
        "symbols": [],
        "footprints": [],
        "3dmodels": [],
    }
    
    # Symbols (.kicad_sym)
    if SYMBOLS_DIR.exists():
        for f in SYMBOLS_DIR.iterdir():
            if f.suffix == ".kicad_sym":
                result["symbols"].append({
                    "name": f.stem,
                    "filename": f.name,
                    "size": f.stat().st_size,
                    "url": f"/kicad_libs/symbols/{f.name}",
                })
    
    # Footprints (.kicad_mod) - can be in root or in .pretty folders
    if FOOTPRINTS_DIR.exists():
        for item in FOOTPRINTS_DIR.iterdir():
            if item.suffix == ".kicad_mod":
                result["footprints"].append({
                    "name": item.stem,
                    "filename": item.name,
                    "size": item.stat().st_size,
                    "url": f"/kicad_libs/footprints/{item.name}",
                })
            elif item.is_dir() and item.suffix == ".pretty":
                # .pretty folder containing .kicad_mod files
                for mod in item.iterdir():
                    if mod.suffix == ".kicad_mod":
                        result["footprints"].append({
                            "name": mod.stem,
                            "filename": mod.name,
                            "library": item.name,
                            "size": mod.stat().st_size,
                            "url": f"/kicad_libs/footprints/{item.name}/{mod.name}",
                        })
    
    # 3D Models (.step, .stp, .wrl)
    if MODELS_DIR.exists():
        for f in MODELS_DIR.iterdir():
            if f.suffix.lower() in (".step", ".stp", ".wrl"):
                result["3dmodels"].append({
                    "name": f.stem,
                    "filename": f.name,
                    "size": f.stat().st_size,
                    "url": f"/kicad_libs/3dmodels/{f.name}",
                })
    
    return jsonify(result)


# ── Staging Endpoints ─────────────────────────────────────────────────

@api_bp.route("/libs/stage/session", methods=["POST"])
def create_staging_session():
    """
    POST /api/v1/libs/stage/session
    
    Create a new staging session for file uploads.
    Returns a session_id to use for subsequent stage operations.
    """
    from services.kicad_staging import create_session
    
    session_id = create_session()
    return jsonify({
        "success": True,
        "session_id": session_id
    })


@api_bp.route("/libs/stage", methods=["POST"])
def stage_lib_file():
    """
    POST /api/v1/libs/stage
    
    Stage a KiCad library file for later processing.
    Files are stored temporarily and processed when the part form is submitted.
    
    Form data:
      - file: The file to stage
      - session_id: Staging session ID (from /libs/stage/session)
      - preview: (optional) If "true", parse and return properties without staging
    
    Returns:
      - For symbols: extracted properties for editing
      - For footprints/3dmodels: staging confirmation
    """
    from services.kicad_staging import stage_file, get_staged_files
    from services.kicad_symbol_processor import KiCadSymbolProcessor
    
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    
    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "Empty filename"}), 400
    
    session_id = request.form.get("session_id", "").strip()
    if not session_id:
        return jsonify({"error": "No session_id provided"}), 400
    
    filename = secure_filename(file.filename)
    _, ext = os.path.splitext(filename)
    ext = ext.lower()
    
    if ext not in EXT_MAP:
        return jsonify({
            "error": f"Unknown file type: {ext}",
            "allowed": list(EXT_MAP.keys()),
        }), 400
    
    file_type, _ = EXT_MAP[ext]
    preview_mode = request.form.get("preview", "").lower() == "true"
    is_text_file = file_type in ("symbols", "footprints")
    
    # Read file content
    content = file.read()
    if is_text_file:
        content_str = content.decode("utf-8")
        content_str = content_str.replace('\r\n', '\n').replace('\r', '\n')
    
    # For symbols, extract properties for preview/editing
    if file_type == "symbols":
        props = KiCadSymbolProcessor.extract_properties(content_str)
        symbol_name = KiCadSymbolProcessor.get_symbol_name(content_str)
        
        if preview_mode:
            return jsonify({
                "preview": True,
                "type": "symbol",
                "filename": filename,
                "symbol_name": symbol_name,
                "properties": props,
                "session_id": session_id
            })
        
        # Stage the symbol file
        result = stage_file(
            session_id, "symbol", filename, content_str, 
            is_text=True, 
            metadata={"symbol_name": symbol_name, "original_props": props}
        )
        result["properties"] = props
        result["symbol_name"] = symbol_name
        return jsonify(result)
    
    elif file_type == "footprints":
        # Stage footprint
        result = stage_file(session_id, "footprint", filename, content_str, is_text=True)
        return jsonify(result)
    
    else:  # 3dmodels
        # Stage 3D model (binary)
        result = stage_file(session_id, "3dmodel", filename, content, is_text=False)
        return jsonify(result)


@api_bp.route("/libs/stage/<session_id>", methods=["GET"])
def get_staged(session_id: str):
    """
    GET /api/v1/libs/stage/<session_id>
    
    Get info about staged files for a session.
    """
    from services.kicad_staging import get_staged_files
    
    meta = get_staged_files(session_id)
    return jsonify(meta)


@api_bp.route("/libs/stage/<session_id>/props", methods=["POST"])
def update_staged_props(session_id: str):
    """
    POST /api/v1/libs/stage/<session_id>/props
    
    Update symbol properties for a staged symbol.
    
    JSON body:
      - symbol_props: dict of property name -> value
    """
    from services.kicad_staging import update_staged_metadata
    
    data = request.get_json() or {}
    symbol_props = data.get("symbol_props", {})
    
    update_staged_metadata(session_id, "symbol", {"symbol_props": symbol_props})
    
    return jsonify({"success": True})


@api_bp.route("/libs/stage/<session_id>", methods=["DELETE"])
def clear_staged(session_id: str):
    """
    DELETE /api/v1/libs/stage/<session_id>
    
    Clear all staged files for a session.
    """
    from services.kicad_staging import clear_session
    
    clear_session(session_id)
    return jsonify({"success": True})


# ── Direct Upload Endpoint ────────────────────────────────────────────

@api_bp.route("/libs/upload", methods=["POST"])
def upload_lib_file():
    """
    POST /api/v1/libs/upload
    
    Upload a KiCad library file. Auto-detects type from extension.
    
    Form data:
      - file: The file to upload
      - dmtuid: (optional) Link to a part's kicad_symbol/footprint field
      - preview: (optional) If "true", parse symbol but don't save yet
      - symbol_props: (optional) JSON of properties to write into symbol
    """
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    
    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "Empty filename"}), 400
    
    filename = secure_filename(file.filename)
    _, ext = os.path.splitext(filename)
    ext = ext.lower()
    
    if ext not in EXT_MAP:
        return jsonify({
            "error": f"Unknown file type: {ext}",
            "allowed": list(EXT_MAP.keys()),
        }), 400
    
    file_type, dest_dir = EXT_MAP[ext]
    preview_mode = request.form.get("preview", "").lower() == "true"
    
    # Ensure directory exists
    dest_dir.mkdir(parents=True, exist_ok=True)
    
    # Initialize custom_props for potential symbol uploads
    custom_props = {}
    symbol_name = None  # Will be set for symbol uploads
    
    # Handle text vs binary files differently
    is_text_file = file_type in ("symbols", "footprints")
    
    if is_text_file:
        # Read as text for symbols and footprints
        content = file.read().decode("utf-8")
        # Normalize line endings (CRLF -> LF) to prevent issues on Windows
        content = content.replace('\r\n', '\n').replace('\r', '\n')
        
        # For symbols, handle preview mode (parse and return properties without saving)
        if file_type == "symbols" and preview_mode:
            from services.kicad_symbol_processor import KiCadSymbolProcessor
            props = KiCadSymbolProcessor.extract_properties(content)
            symbol_name = KiCadSymbolProcessor.get_symbol_name(content)
            
            return jsonify({
                "preview": True,
                "type": file_type,
                "filename": filename,
                "name": Path(filename).stem,
                "symbol_name": symbol_name,
                "properties": props,
            })
        
        # Apply custom properties to symbol if provided
        symbol_props_json = request.form.get("symbol_props", "").strip()
        dmtuid = request.form.get("dmtuid", "").strip()
        
        # For symbols: auto-generate Value from database if dmtuid provided
        if file_type == "symbols" and dmtuid:
            import json as json_mod
            from db import get_session
            from db.models import Part
            
            session = get_session()
            try:
                part = session.query(Part).filter(Part.dmtuid == dmtuid).first()
                if part:
                    part_data = part.to_dict()
                    auto_value = _generate_symbol_value(part_data)
                    
                    # Parse existing symbol_props and add auto-value if no Value specified
                    if symbol_props_json:
                        try:
                            custom_props = json_mod.loads(symbol_props_json)
                        except json_mod.JSONDecodeError:
                            custom_props = {}
                    
                    # Only auto-set Value if not explicitly provided
                    if auto_value and not custom_props.get("Value"):
                        custom_props["Value"] = auto_value
                    
                    # Also auto-set MPN if not provided
                    if part_data.get("mpn") and not custom_props.get("MPN"):
                        custom_props["MPN"] = part_data.get("mpn")
                    
                    # Re-serialize for the property-setting loop below
                    symbol_props_json = json_mod.dumps(custom_props)
            finally:
                session.close()
        
        if file_type == "symbols" and symbol_props_json:
            import json
            from services.kicad_symbol_processor import KiCadSymbolProcessor
            try:
                custom_props = json.loads(symbol_props_json)
                for prop_name, prop_value in custom_props.items():
                    if prop_value:  # Only set non-empty values
                        content = KiCadSymbolProcessor._set_property(content, prop_name, prop_value)
            except json.JSONDecodeError:
                pass
        
        # For symbols, generate filename from Value + package
        if file_type == "symbols" and custom_props:
            value = custom_props.get("Value", "").strip()
            # Try to extract package from Footprint (e.g., "DMTDB:C_1206_3216Metric" -> "1206")
            footprint = custom_props.get("Footprint", "")
            package = ""
            if footprint:
                # Extract package size (e.g., 1206, 0805, etc.)
                pkg_match = re.search(r'(\d{4})(?:_|Metric|$)', footprint)
                if pkg_match:
                    package = pkg_match.group(1)
            
            if value:
                # Combine Value and package for filename
                if package and package not in value:
                    new_name = f"{value} {package}"
                else:
                    new_name = value
                
                # Sanitize filename (replace chars not allowed in filenames)
                new_name = re.sub(r'[<>:"/\\|?*]', '_', new_name)
                new_name = new_name.strip()
                
                if new_name:
                    filename = f"{new_name}.kicad_sym"
        
        # Handle file type specific logic
        dest_path = dest_dir / filename
        
        if file_type == "symbols":
            # Symbols are ALWAYS consolidated into DMTDB_{Domain}_{Family}.kicad_sym
            from services.kicad_symbol_processor import KiCadSymbolProcessor
            from schema.loader import domain_name, family_name
            
            # Determine library filename from DMTUID or direct TT/FF params
            dmtuid = request.form.get("dmtuid", "").strip()
            tt = request.form.get("tt", "").strip()
            ff = request.form.get("ff", "").strip()
            
            if dmtuid and len(dmtuid) >= 10:
                # Parse DMTUID: DMT-TTFFCCIII... -> TT=positions 4-5, FF=6-7
                tt = dmtuid[4:6]
                ff = dmtuid[6:8]
            
            if tt and ff:
                dom_name = domain_name(tt)
                fam_name = family_name(tt, ff)
                # Sanitize names (remove spaces/special chars)
                dom_name = re.sub(r'[^a-zA-Z0-9]', '', dom_name)
                fam_name = re.sub(r'[^a-zA-Z0-9]', '', fam_name)
                lib_filename = f"DMTDB_{dom_name}_{fam_name}.kicad_sym"
            else:
                lib_filename = "DMTDB.kicad_sym"
            
            # Symbol name based on component type:
            # - Passives (Capacitors/Resistors/Inductors): use "Value MPN" for uniqueness
            # - All others: use MPN
            value_name = custom_props.get("Value", "").strip() if custom_props else ""
            mpn = custom_props.get("MPN", "").strip() if custom_props else ""
            mpn_sanitized = re.sub(r'[<>:"/\\|?*]', '_', mpn)  # Sanitize
            
            if tt == "01" and ff in ("01", "02", "03") and value_name and mpn_sanitized:
                # Passives: use "Value MPN" for unique symbols (e.g., "4.7K 1% GWCR0402-4K7FT10")
                symbol_name = f"{value_name} {mpn_sanitized}"
            elif mpn_sanitized:
                # Non-passives or passives without value: use MPN
                symbol_name = mpn_sanitized
            elif value_name:
                # Fallback for passives without MPN
                symbol_name = value_name
            else:
                # Fallback: filename stem
                symbol_name = Path(filename).stem
            
            # Update symbol name in content
            content = KiCadSymbolProcessor.set_symbol_name(content, symbol_name)
            
            # Update Footprint property to use DMTDB: prefix
            footprint = custom_props.get("Footprint", "") if custom_props else ""
            if footprint and not footprint.startswith("DMTDB:"):
                fp_name = footprint.split(":")[-1] if ":" in footprint else footprint
                dmtdb_footprint = f"DMTDB:{fp_name}"
                content = KiCadSymbolProcessor._set_property(content, "Footprint", dmtdb_footprint)
            
            # Extract symbol block and add to library
            symbol_block = KiCadSymbolProcessor.extract_symbol_block(content)
            if not symbol_block:
                return jsonify({"error": "Could not extract symbol from uploaded file"}), 400
            
            library_path = SYMBOLS_DIR / lib_filename
            
            # Add/replace symbol in library (duplicate detection is handled inside)
            KiCadSymbolProcessor.add_symbol_to_library(library_path, symbol_block, symbol_name)
            
            # Set filename for result (for db reference)
            filename = lib_filename
            dest_path = library_path
        
        elif file_type == "footprints":
            # For footprints: if file already exists, just reuse it (no duplication)
            if dest_path.exists():
                result = {
                    "success": True,
                    "type": file_type,
                    "filename": filename,
                    "name": Path(filename).stem,
                    "url": f"/kicad_libs/{file_type}/{filename}",
                    "size": dest_path.stat().st_size,
                    "reused": True,
                    "message": f"File already exists, using existing {filename}",
                }
                dmtuid = request.form.get("dmtuid", "").strip()
                if dmtuid:
                    from db import get_session
                    from db.models import Part
                    session = get_session()
                    try:
                        part = session.query(Part).filter(Part.dmtuid == dmtuid).first()
                        if part:
                            part.kicad_footprint = f"DMTDB:{Path(filename).stem}"
                            result["linked_field"] = "kicad_footprint"
                            result["linked_value"] = part.kicad_footprint
                            session.commit()
                    finally:
                        session.close()
                return jsonify(result), 200
            
            # Update 3D model path in footprints to use DMTDB environment variable
            # If model_filename is provided, use that; otherwise extract from existing path
            model_filename = request.form.get("model_filename", "").strip()
            
            if model_filename:
                # Replace any existing model path with the specified filename
                model_pattern = r'\(model\s+"[^"]*"'
                model_replacement = f'(model "${{DMTDB_3D}}/{model_filename}"'
                content = re.sub(model_pattern, model_replacement, content, flags=re.IGNORECASE)
            else:
                # Default: preserve original filename but normalize path
                # Replace absolute model paths with ${DMTDB_3D}/filename.ext
                # Matches: (model "any/path/to/model.step"
                model_pattern = r'\(model\s+"[^"]*[/\\]([^"/\\]+\.[^"]+)"'
                model_replacement = r'(model "${DMTDB_3D}/\1"'
                content = re.sub(model_pattern, model_replacement, content, flags=re.IGNORECASE)
            
            # Save footprint file
            dest_path.write_text(content, encoding="utf-8")
    else:
        # Save binary files (3D models) directly
        dest_path = dest_dir / filename
        
        # For 3D models: if file already exists, just reuse it (no duplication)
        if dest_path.exists():
            result = {
                "success": True,
                "type": file_type,
                "filename": filename,
                "name": Path(filename).stem,
                "url": f"/kicad_libs/{file_type}/{filename}",
                "size": dest_path.stat().st_size,
                "reused": True,
                "message": f"File already exists, using existing {filename}",
            }
            
            # Still update part record with reference to existing file
            dmtuid = request.form.get("dmtuid", "").strip()
            if dmtuid:
                from db import get_session
                from db.models import Part
                session = get_session()
                try:
                    part = session.query(Part).filter(Part.dmtuid == dmtuid).first()
                    if part:
                        part.kicad_3dmodel = filename
                        result["linked_field"] = "kicad_3dmodel"
                        result["linked_value"] = filename
                        session.commit()
                finally:
                    session.close()
            
            return jsonify(result), 200
        
        file.save(dest_path)
    
    result = {
        "success": True,
        "type": file_type,
        "filename": filename,
        "name": symbol_name if file_type == "symbols" else Path(filename).stem,
        "url": f"/kicad_libs/{file_type}/{filename}",
        "size": dest_path.stat().st_size,
    }
    
    # For symbols, always include the correct linked_value format (even without dmtuid)
    if file_type == "symbols":
        lib_name = Path(lib_filename).stem  # e.g., DMTDB_PassiveComponents_Resistors
        result["linked_value"] = f"{lib_name}:{symbol_name}"
    
    # If dmtuid provided, update the part's KiCad fields
    dmtuid = request.form.get("dmtuid", "").strip()
    
    if dmtuid:
        from db import get_session
        from db.models import Part
        
        session = get_session()
        try:
            part = session.query(Part).filter(Part.dmtuid == dmtuid).first()
            if part:
                name = symbol_name if file_type == "symbols" else Path(filename).stem
                if file_type == "symbols":
                    # Library name is the consolidated library filename without .kicad_sym extension
                    lib_name = Path(lib_filename).stem  # e.g., DMTDB_PassiveComponents_Resistors
                    part.kicad_symbol = f"{lib_name}:{symbol_name}"
                    result["linked_field"] = "kicad_symbol"
                    result["linked_value"] = part.kicad_symbol
                    # Also save LCSC_PART if provided
                    lcsc_part = custom_props.get("LCSC_PART", "").strip() if custom_props else ""
                    if lcsc_part:
                        part.kicad_libref = lcsc_part
                        result["lcsc_part"] = lcsc_part
                elif file_type == "footprints":
                    part.kicad_footprint = f"DMTDB:{name}"
                    result["linked_field"] = "kicad_footprint"
                    result["linked_value"] = part.kicad_footprint
                elif file_type == "3dmodels":
                    part.kicad_3dmodel = filename  # Store full filename with extension
                    result["linked_field"] = "kicad_3dmodel"
                    result["linked_value"] = part.kicad_3dmodel
                session.commit()
        finally:
            session.close()
    
    return jsonify(result), 201


@api_bp.route("/libs/<file_type>/<filename>", methods=["DELETE"])
def delete_lib_file(file_type: str, filename: str):
    """
    DELETE /api/v1/libs/{type}/{filename}
    
    Delete a library file.
    """
    type_dirs = {
        "symbols": SYMBOLS_DIR,
        "footprints": FOOTPRINTS_DIR,
        "3dmodels": MODELS_DIR,
    }
    
    if file_type not in type_dirs:
        return jsonify({"error": f"Invalid type: {file_type}"}), 400
    
    filepath = type_dirs[file_type] / secure_filename(filename)
    
    if not filepath.exists():
        return jsonify({"error": "File not found"}), 404
    
    filepath.unlink()
    return jsonify({"success": True, "deleted": filename})


@api_bp.route("/libs/symbols/<filename>/sync", methods=["POST"])
def sync_symbol_with_part(filename: str):
    """
    POST /api/v1/libs/symbols/{filename}/sync
    
    Re-process a symbol file with data from a linked part.
    
    JSON body:
      - dmtuid: The part to pull data from
    """
    from db import get_session
    from db.models import Part
    from services.kicad_symbol_processor import process_uploaded_symbol
    
    data = request.get_json(force=True) if request.is_json else {}
    dmtuid = data.get("dmtuid", "").strip()
    
    if not dmtuid:
        return jsonify({"error": "dmtuid required"}), 400
    
    filepath = SYMBOLS_DIR / secure_filename(filename)
    if not filepath.exists():
        return jsonify({"error": "Symbol file not found"}), 404
    
    session = get_session()
    try:
        part = session.query(Part).filter(Part.dmtuid == dmtuid).first()
        if not part:
            return jsonify({"error": "Part not found"}), 404
        
        result = process_uploaded_symbol(filepath, part)
        
        return jsonify({
            "success": True,
            "filename": filename,
            "symbol_name": result["symbol_name"],
            "filled_properties": {
                k: v for k, v in result["updated_properties"].items()
                if v and k in ["Value", "Footprint", "Datasheet", "Description", "MFR", "MPN", "ROHS"]
            },
        })
    finally:
        session.close()


@api_bp.route("/libs/link", methods=["POST"])
def link_existing_lib():
    """
    POST /api/v1/libs/link
    
    Link an existing library file to a part without re-uploading.
    
    Form data:
      - dmtuid: The part to link to
      - filename: The existing library filename
      - type: 'symbols', 'footprints', or '3dmodels'
      - symbol_name: (symbols only) The symbol name within the library
    """
    from db import get_session
    from db.models import Part
    
    dmtuid = request.form.get("dmtuid", "").strip()
    filename = request.form.get("filename", "").strip()
    file_type = request.form.get("type", "").strip()
    symbol_name = request.form.get("symbol_name", "").strip()
    
    if not dmtuid or not filename or not file_type:
        return jsonify({"error": "dmtuid, filename, and type required"}), 400
    
    if file_type not in ("symbols", "footprints", "3dmodels"):
        return jsonify({"error": "Invalid type"}), 400
    
    # Verify file exists
    type_dirs = {
        "symbols": SYMBOLS_DIR,
        "footprints": FOOTPRINTS_DIR,
        "3dmodels": MODELS_DIR,
    }
    filepath = type_dirs[file_type] / filename
    if not filepath.exists():
        return jsonify({"error": "File not found"}), 404
    
    session = get_session()
    try:
        part = session.query(Part).filter(Part.dmtuid == dmtuid).first()
        if not part:
            return jsonify({"error": "Part not found"}), 404
        
        name = Path(filename).stem
        
        if file_type == "symbols":
            lib_name = Path(filename).stem  # e.g., DMTDB_PassiveComponents_Resistors
            if symbol_name:
                part.kicad_symbol = f"{lib_name}:{symbol_name}"
            else:
                # Fallback: use lib_name as symbol_name (legacy behavior)
                part.kicad_symbol = f"{lib_name}:{lib_name}"
        elif file_type == "footprints":
            part.kicad_footprint = f"DMTDB:{name}"
        elif file_type == "3dmodels":
            part.kicad_3dmodel = filename
        
        session.commit()
        
        return jsonify({
            "success": True,
            "type": file_type,
            "filename": filename,
            "name": name,
        })
    finally:
        session.close()
