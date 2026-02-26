<#
.SYNOPSIS
    Sync DMTDB KiCad libraries from server via SSH/SCP.
    
.DESCRIPTION
    Uses scp (built into Windows 10+) to download library files from the server,
    then registers new symbol libraries in KiCad.
    
.EXAMPLE
    .\sync-from-server.ps1
    
.EXAMPLE
    .\sync-from-server.ps1 -LocalPath "D:\KiCad\DMTDB"
#>

param(
    [string]$SshHost = "masterpi@192.168.0.25",
    [string]$RemotePath = "/home/masterpi/SW_PartsDB/kicad_libs",
    [string]$LocalPath = ""
)

$ErrorActionPreference = "Stop"

# ============================================================================
# Configuration - Edit these to match your setup
# ============================================================================

if (-not $LocalPath) {
    $LocalPath = Join-Path $env:USERPROFILE "Documents\KiCad\DMTDB"
}

# ============================================================================

function Write-Info { param([string]$m) Write-Host "[INFO] $m" -ForegroundColor Cyan }
function Write-OK { param([string]$m) Write-Host "[OK] $m" -ForegroundColor Green }
function Write-Warn { param([string]$m) Write-Host "[WARN] $m" -ForegroundColor Yellow }

Write-Host ""
Write-Host "======================================" -ForegroundColor Cyan
Write-Host "  DMTDB Library Sync (SSH)" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""
Write-Info "Server: ${SshHost}:${RemotePath}"
Write-Info "Local:  $LocalPath"
Write-Host ""

# Create directories
$symbolsDir = Join-Path $LocalPath "symbols"
$footprintsDir = Join-Path $LocalPath "footprints"
$modelsDir = Join-Path $LocalPath "3dmodels"

foreach ($dir in @($symbolsDir, $footprintsDir, $modelsDir)) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
}

# Check for rsync (Git Bash) or fall back to scp
$useRsync = $false
$rsyncPath = $null

# Check common rsync locations
$rsyncLocations = @(
    "C:\Program Files\Git\usr\bin\rsync.exe",
    "C:\Program Files (x86)\Git\usr\bin\rsync.exe",
    "$env:LOCALAPPDATA\Programs\Git\usr\bin\rsync.exe"
)
foreach ($loc in $rsyncLocations) {
    if (Test-Path $loc) {
        $rsyncPath = $loc
        $useRsync = $true
        break
    }
}

if ($useRsync) {
    Write-Info "Using rsync for efficient sync"
    
    # Convert Windows paths to Unix style for rsync
    $localUnix = $LocalPath -replace '\\', '/' -replace '^([A-Z]):', '/$1'
    
    Write-Info "Syncing symbols..."
    & $rsyncPath -avz "${SshHost}:${RemotePath}/symbols/" "$symbolsDir/"
    
    Write-Info "Syncing footprints..."
    & $rsyncPath -avz "${SshHost}:${RemotePath}/footprints/" "$footprintsDir/"
    
    Write-Info "Syncing 3D models..."
    & $rsyncPath -avz "${SshHost}:${RemotePath}/3dmodels/" "$modelsDir/"
}
else {
    Write-Info "Using scp (rsync not found - install Git for faster syncs)"
    
    # Use scp - downloads everything each time
    Write-Info "Syncing symbols..."
    scp -r "${SshHost}:${RemotePath}/symbols/*" "$symbolsDir/"
    
    Write-Info "Syncing footprints..."
    scp -r "${SshHost}:${RemotePath}/footprints/*" "$footprintsDir/"
    
    Write-Info "Syncing 3D models..."
    scp -r "${SshHost}:${RemotePath}/3dmodels/*" "$modelsDir/"
}

Write-OK "Files synced"

# ── Update KiCad Configuration ─────────────────────────────────────────────

$kicadBase = Join-Path $env:APPDATA "kicad"
$kicadConfig = $null

if (Test-Path $kicadBase) {
    $versions = Get-ChildItem -Path $kicadBase -Directory | 
    Where-Object { $_.Name -match '^\d+\.\d+$' } |
    Sort-Object { [version]$_.Name } -Descending
    
    if ($versions.Count -gt 0) {
        $kicadConfig = $versions[0].FullName
    }
}

if ($kicadConfig) {
    Write-Info "KiCad config: $kicadConfig"
    
    $symLibTable = Join-Path $kicadConfig "sym-lib-table"
    
    # Parse existing libraries
    $existing = @()
    if (Test-Path $symLibTable) {
        $content = Get-Content $symLibTable -Raw
        $matches = [regex]::Matches($content, '\(name\s+"([^"]+)"\)')
        $existing = $matches | ForEach-Object { $_.Groups[1].Value }
    }
    
    # Add new symbol libraries
    $newCount = 0
    $symFiles = Get-ChildItem -Path $symbolsDir -Filter "*.kicad_sym" -ErrorAction SilentlyContinue
    
    foreach ($file in $symFiles) {
        $libName = $file.BaseName
        
        if ($libName -notin $existing) {
            Write-Info "Adding: $libName"
            
            # UTF-8 without BOM (KiCad doesn't like BOM)
            $utf8NoBom = New-Object System.Text.UTF8Encoding $false
            
            if (-not (Test-Path $symLibTable)) {
                [System.IO.File]::WriteAllText($symLibTable, "(sym_lib_table`n  (version 7)`n)", $utf8NoBom)
            }
            
            # Read file, remove last line (closing paren), add entry, add closing paren
            $lines = Get-Content $symLibTable
            $lines = $lines[0..($lines.Count - 2)]
            $lines += "  (lib (name `"$libName`")(type `"KiCad`")(uri `"`${DMTDB_SYM}/$($file.Name)`")(options `"`")(descr `"`")(hidden))"
            $lines += ")"
            [System.IO.File]::WriteAllLines($symLibTable, $lines, $utf8NoBom)
            
            $newCount++
        }
    }
    
    if ($newCount -gt 0) {
        Write-OK "Added $newCount new symbol libraries"
    }
    
    # Update path variables
    $commonFile = Join-Path $kicadConfig "kicad_common.json"
    if (Test-Path $commonFile) {
        $json = Get-Content $commonFile -Raw | ConvertFrom-Json
        
        if (-not $json.environment) {
            $json | Add-Member -NotePropertyName "environment" -NotePropertyValue @{} -Force
        }
        if (-not $json.environment.vars) {
            $json.environment | Add-Member -NotePropertyName "vars" -NotePropertyValue @{} -Force
        }
        
        $symPath = $symbolsDir -replace '\\', '/'
        $fpPath = $footprintsDir -replace '\\', '/'
        $m3dPath = $modelsDir -replace '\\', '/'
        
        $json.environment.vars | Add-Member -NotePropertyName "DMTDB_SYM" -NotePropertyValue $symPath -Force
        $json.environment.vars | Add-Member -NotePropertyName "DMTDB_FOOTPRINT" -NotePropertyValue $fpPath -Force
        $json.environment.vars | Add-Member -NotePropertyName "DMTDB_3D" -NotePropertyValue $m3dPath -Force
        
        Copy-Item $commonFile "$commonFile.bak" -Force
        # Write without BOM
        $utf8NoBom = New-Object System.Text.UTF8Encoding $false
        [System.IO.File]::WriteAllText($commonFile, ($json | ConvertTo-Json -Depth 10), $utf8NoBom)
        Write-OK "Updated KiCad path variables"
    }
}
else {
    Write-Warn "KiCad config not found. Set paths manually in Preferences → Configure Paths:"
    Write-Host "  DMTDB_SYM       = $($symbolsDir -replace '\\', '/')"
    Write-Host "  DMTDB_FOOTPRINT = $($footprintsDir -replace '\\', '/')"
    Write-Host "  DMTDB_3D        = $($modelsDir -replace '\\', '/')"
}

Write-Host ""
Write-Host "======================================" -ForegroundColor Green
Write-Host "  Sync Complete!" -ForegroundColor Green
Write-Host "======================================" -ForegroundColor Green
Write-Host ""
Write-Host "Restart KiCad to see new libraries." -ForegroundColor Yellow
Write-Host ""
