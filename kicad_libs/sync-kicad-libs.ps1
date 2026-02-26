#Requires -Version 5.1
<#
.SYNOPSIS
    Syncs DMTDB KiCad libraries from server and registers them in KiCad.
    
.DESCRIPTION
    This script:
    1. Fetches your PC's configured paths from the DMTDB server (set via Client Setup page)
    2. Downloads new/updated symbol, footprint, and 3D model files
    3. Registers new symbol libraries in KiCad's sym-lib-table (hidden by default)
    4. Configures KiCad path variables (DMTDB_SYM, DMTDB_FOOTPRINT, DMTDB_3D)
    5. Marks the client as synced on the server
    
.PARAMETER ServerUrl
    URL of the DMTDB server (default: http://192.168.0.25:5000)
    
.PARAMETER LibsPath
    Override the server-configured base path. If not set, uses paths from Client Setup.
    
.PARAMETER KiCadVersion
    KiCad version (e.g., "8.0", "9.0"). Auto-detected if not specified.
    
.PARAMETER Force
    Skip sync check and download all files regardless of hash.
    
.EXAMPLE
    .\sync-kicad-libs.ps1
    # Uses paths configured in DMTDB Client Setup page
    
.EXAMPLE
    .\sync-kicad-libs.ps1 -ServerUrl "http://192.168.0.25:5000" -Force
#>

[CmdletBinding()]
param(
    [string]$ServerUrl = "http://192.168.0.25:5000",
    [string]$LibsPath = "",
    [string]$KiCadVersion = "",
    [switch]$Force
)

$ErrorActionPreference = "Stop"

# ============================================================================
# Configuration
# ============================================================================

$ServerUrl = $ServerUrl.TrimEnd('/')

# Paths will be fetched from server config or use defaults
$SymbolsPath = ""
$FootprintsPath = ""
$ModelsPath = ""

# ============================================================================
# Helper Functions
# ============================================================================

function Write-ColorOutput {
    param([string]$Message, [string]$Color = "White")
    Write-Host $Message -ForegroundColor $Color
}

function Write-Info { param([string]$Message) Write-ColorOutput "[INFO] $Message" "Cyan" }
function Write-Success { param([string]$Message) Write-ColorOutput "[OK] $Message" "Green" }
function Write-Warn { param([string]$Message) Write-ColorOutput "[WARN] $Message" "Yellow" }
function Write-Error { param([string]$Message) Write-ColorOutput "[ERROR] $Message" "Red" }

function Test-ServerConnection {
    param([string]$Url)
    try {
        $response = Invoke-RestMethod -Uri "$Url/api/v1/libs" -Method Get -TimeoutSec 5
        return $true
    }
    catch {
        return $false
    }
}

function Get-ClientConfig {
    <#
    .SYNOPSIS
        Get configured paths for this PC from the server (set via Client Setup page)
    #>
    try {
        $response = Invoke-RestMethod -Uri "$ServerUrl/api/v1/libs/client" -Method Get -TimeoutSec 5
        return $response
    }
    catch {
        Write-Warn "Could not fetch client config from server"
        return $null
    }
}

function Get-KiCadConfigPath {
    <#
    .SYNOPSIS
        Find KiCad configuration directory
    #>
    $appData = $env:APPDATA
    $kicadBase = Join-Path $appData "kicad"
    
    if (-not (Test-Path $kicadBase)) {
        return $null
    }
    
    # Find installed versions (newest first)
    $versions = Get-ChildItem -Path $kicadBase -Directory | 
    Where-Object { $_.Name -match '^\d+\.\d+$' } |
    Sort-Object { [version]$_.Name } -Descending
    
    if ($KiCadVersion) {
        $targetDir = Join-Path $kicadBase $KiCadVersion
        if (Test-Path $targetDir) {
            return $targetDir
        }
        Write-Warn "KiCad version $KiCadVersion not found, using latest"
    }
    
    if ($versions.Count -gt 0) {
        return $versions[0].FullName
    }
    
    return $null
}

function Get-LibsFromServer {
    <#
    .SYNOPSIS
        Get list of library files from server
    #>
    try {
        $response = Invoke-RestMethod -Uri "$ServerUrl/api/v1/libs" -Method Get
        return $response
    }
    catch {
        throw "Failed to get library list from server: $_"
    }
}

function Get-SyncStatus {
    <#
    .SYNOPSIS
        Check if sync is needed
    #>
    try {
        $response = Invoke-RestMethod -Uri "$ServerUrl/api/v1/libs/sync/status" -Method Get
        return $response
    }
    catch {
        Write-Warn "Could not check sync status, will sync all files"
        return @{ needs_sync = $true; files = @() }
    }
}

function Download-File {
    param(
        [string]$Url,
        [string]$Destination
    )
    
    $dir = Split-Path $Destination -Parent
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
    
    try {
        Invoke-WebRequest -Uri $Url -OutFile $Destination -UseBasicParsing
        return $true
    }
    catch {
        Write-Warn "Failed to download $Url : $_"
        return $false
    }
}

function Parse-SymLibTable {
    <#
    .SYNOPSIS
        Parse KiCad sym-lib-table file and return entries
    #>
    param([string]$Path)
    
    $entries = @()
    
    if (-not (Test-Path $Path)) {
        return $entries
    }
    
    $content = Get-Content $Path -Raw
    
    # Match each (lib ...) entry
    $pattern = '\(lib\s*\(name\s+"?([^")]+)"?\)\s*\(type\s+"?([^")]+)"?\)\s*\(uri\s+"?([^")]+)"?\)(?:\s*\(options\s+"?([^")]*)"?\))?(?:\s*\(descr\s+"?([^")]*)"?\))?\)'
    
    $matches = [regex]::Matches($content, $pattern)
    
    foreach ($m in $matches) {
        $entries += [PSCustomObject]@{
            Name        = $m.Groups[1].Value
            Type        = $m.Groups[2].Value
            Uri         = $m.Groups[3].Value
            Options     = $m.Groups[4].Value
            Description = $m.Groups[5].Value
        }
    }
    
    return $entries
}

function Write-SymLibTable {
    <#
    .SYNOPSIS
        Write KiCad sym-lib-table file
    #>
    param(
        [string]$Path,
        [array]$Entries
    )
    
    $lines = @("(sym_lib_table")
    $lines += "  (version 7)"
    
    foreach ($entry in $Entries) {
        $line = "  (lib (name `"$($entry.Name)`")(type `"$($entry.Type)`")(uri `"$($entry.Uri)`")"
        
        if ($entry.Options) {
            $line += "(options `"$($entry.Options)`")"
        }
        
        if ($entry.Description) {
            $line += "(descr `"$($entry.Description)`")"
        }
        
        $line += ")"
        $lines += $line
    }
    
    $lines += ")"
    
    # Backup existing file
    if (Test-Path $Path) {
        $backup = "$Path.bak"
        Copy-Item $Path $backup -Force
    }
    
    $lines | Out-File -FilePath $Path -Encoding utf8 -Force
}

function Update-SymLibTable {
    <#
    .SYNOPSIS
        Update sym-lib-table with new DMTDB symbol libraries
    #>
    param(
        [string]$KiCadConfigPath,
        [string]$SymbolsPath
    )
    
    $symLibTable = Join-Path $KiCadConfigPath "sym-lib-table"
    
    # Get existing entries
    $entries = @(Parse-SymLibTable -Path $symLibTable)
    
    # Get DMTDB symbol files from local folder
    $symbolFiles = Get-ChildItem -Path $SymbolsPath -Filter "*.kicad_sym" -ErrorAction SilentlyContinue
    
    if (-not $symbolFiles) {
        Write-Warn "No symbol files found in $SymbolsPath"
        return 0
    }
    
    $newCount = 0
    
    foreach ($file in $symbolFiles) {
        $libName = $file.BaseName
        
        # Check if already registered
        $existing = $entries | Where-Object { $_.Name -eq $libName }
        
        if (-not $existing) {
            Write-Info "Adding new symbol library: $libName"
            
            $entries += [PSCustomObject]@{
                Name        = $libName
                Type        = "KiCad"
                Uri         = "`${DMTDB_SYM}/$($file.Name)"
                Options     = "hide"
                Description = "DMTDB - $libName"
            }
            $newCount++
        }
    }
    
    if ($newCount -gt 0) {
        Write-SymLibTable -Path $symLibTable -Entries $entries
        Write-Success "Added $newCount new symbol libraries to sym-lib-table"
    }
    
    return $newCount
}

function Update-KiCadPaths {
    <#
    .SYNOPSIS
        Add/update KiCad path variables in kicad_common file
    #>
    param(
        [string]$KiCadConfigPath,
        [string]$SymbolsPath,
        [string]$FootprintsPath,
        [string]$ModelsPath
    )
    
    $commonFile = Join-Path $KiCadConfigPath "kicad_common.json"
    
    $pathVars = @{
        "DMTDB_SYM"       = $SymbolsPath -replace '\\', '/'
        "DMTDB_FOOTPRINT" = $FootprintsPath -replace '\\', '/'
        "DMTDB_3D"        = $ModelsPath -replace '\\', '/'
    }
    
    if (Test-Path $commonFile) {
        $content = Get-Content $commonFile -Raw | ConvertFrom-Json
        
        # Ensure environment.vars exists
        if (-not $content.environment) {
            $content | Add-Member -NotePropertyName "environment" -NotePropertyValue @{} -Force
        }
        if (-not $content.environment.vars) {
            $content.environment | Add-Member -NotePropertyName "vars" -NotePropertyValue @{} -Force
        }
        
        $updated = $false
        foreach ($key in $pathVars.Keys) {
            $currentValue = $content.environment.vars.$key
            if ($currentValue -ne $pathVars[$key]) {
                $content.environment.vars | Add-Member -NotePropertyName $key -NotePropertyValue $pathVars[$key] -Force
                Write-Info "Setting $key = $($pathVars[$key])"
                $updated = $true
            }
        }
        
        if ($updated) {
            # Backup
            Copy-Item $commonFile "$commonFile.bak" -Force
            $content | ConvertTo-Json -Depth 10 | Out-File $commonFile -Encoding utf8 -Force
            Write-Success "Updated KiCad path variables"
        }
    }
    else {
        Write-Warn "kicad_common.json not found at $KiCadConfigPath"
        Write-Info "Please set the following path variables manually in KiCad (Preferences -> Configure Paths):"
        foreach ($key in $pathVars.Keys) {
            Write-Host "  $key = $($pathVars[$key])"
        }
    }
}

function Mark-ClientSynced {
    <#
    .SYNOPSIS
        Mark this client as synced on the server
    #>
    try {
        $response = Invoke-RestMethod -Uri "$ServerUrl/api/v1/libs/client/mark-synced" -Method Post
        Write-Info "Marked as synced on server (hash: $($response.libs_hash))"
    }
    catch {
        Write-Warn "Could not mark sync status on server: $_"
    }
}

# ============================================================================
# Main Script
# ============================================================================

Write-Host ""
Write-Host "======================================" -ForegroundColor Cyan
Write-Host "  DMTDB KiCad Library Sync" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""

# Check server connection
Write-Info "Connecting to server at $ServerUrl..."
if (-not (Test-ServerConnection -Url $ServerUrl)) {
    Write-Error "Cannot connect to server at $ServerUrl"
    Write-Host "Make sure the DMTDB server is running and accessible."
    exit 1
}
Write-Success "Server connection OK"

# Fetch client configuration from server
Write-Host ""
Write-Info "Fetching your PC's configuration from server..."
$clientConfig = Get-ClientConfig

if ($clientConfig -and $clientConfig.found) {
    $pcName = $clientConfig.config.client_name
    if ($pcName) {
        Write-Success "Found configuration for: $pcName"
    }
    else {
        Write-Success "Found configuration for this PC"
    }
    
    # Use paths from server config unless overridden by command line
    if (-not $LibsPath) {
        $SymbolsPath = $clientConfig.config.path_symbols
        $FootprintsPath = $clientConfig.config.path_footprints
        $ModelsPath = $clientConfig.config.path_3dmodels
    }
}
else {
    Write-Warn "No configuration found for this PC on the server"
    Write-Info "Set up your paths at: $ServerUrl/setup"
}

# Fall back to defaults if no paths configured
if (-not $SymbolsPath -and -not $LibsPath) {
    $LibsPath = Join-Path $env:USERPROFILE "Documents\KiCad\DMTDB"
    Write-Info "Using default path: $LibsPath"
}

if ($LibsPath) {
    $SymbolsPath = Join-Path $LibsPath "symbols"
    $FootprintsPath = Join-Path $LibsPath "footprints"
    $ModelsPath = Join-Path $LibsPath "3dmodels"
}

# Validate we have paths
if (-not $SymbolsPath -or -not $FootprintsPath -or -not $ModelsPath) {
    Write-Error "No library paths configured!"
    Write-Host "Please configure paths at: $ServerUrl/setup"
    Write-Host "Or use -LibsPath parameter to specify a local path."
    exit 1
}

Write-Info "Symbols path:    $SymbolsPath"
Write-Info "Footprints path: $FootprintsPath"
Write-Info "3D Models path:  $ModelsPath"

# Find KiCad config
$kicadConfig = Get-KiCadConfigPath
if ($kicadConfig) {
    Write-Info "KiCad config found at: $kicadConfig"
}
else {
    Write-Warn "KiCad configuration not found. Libraries will be downloaded but not auto-registered."
}

# Check sync status
Write-Host ""
$syncStatus = Get-SyncStatus

if (-not $Force -and -not $syncStatus.needs_sync) {
    Write-Success "Libraries are already in sync (hash: $($syncStatus.current_hash))"
    Write-Host "Use -Force to re-download all files anyway."
    exit 0
}

if ($syncStatus.needs_sync) {
    Write-Info "Libraries need to be synced"
    if ($syncStatus.last_sync) {
        Write-Info "Last sync: $($syncStatus.last_sync)"
    }
}

# Create directories
Write-Host ""
Write-Info "Setting up directories..."

foreach ($dir in @($SymbolsPath, $FootprintsPath, $ModelsPath)) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        Write-Info "Created: $dir"
    }
}

# Get library list from server
Write-Host ""
Write-Info "Fetching library list from server..."
$libs = Get-LibsFromServer

# Download files
Write-Host ""
$downloadCount = @{ symbols = 0; footprints = 0; models = 0 }

# Symbols
Write-Info "Syncing symbol libraries..."
foreach ($sym in $libs.symbols) {
    $localFile = Join-Path $SymbolsPath $sym.filename
    $url = "$ServerUrl/kicad_libs/symbols/$($sym.filename)"
    
    # Check if file needs update (simple size check)
    $needsDownload = $Force -or (-not (Test-Path $localFile)) -or ((Get-Item $localFile -ErrorAction SilentlyContinue).Length -ne $sym.size)
    
    if ($needsDownload) {
        Write-Host "  Downloading: $($sym.filename)" -ForegroundColor Gray
        if (Download-File -Url $url -Destination $localFile) {
            $downloadCount.symbols++
        }
    }
}
Write-Success "Symbols: $($downloadCount.symbols) downloaded, $($libs.symbols.Count) total"

# Footprints
Write-Info "Syncing footprint libraries..."
foreach ($fp in $libs.footprints) {
    $localFile = Join-Path $FootprintsPath $fp.filename
    $url = "$ServerUrl/kicad_libs/footprints/$($fp.filename)"
    
    $needsDownload = $Force -or (-not (Test-Path $localFile)) -or ((Get-Item $localFile -ErrorAction SilentlyContinue).Length -ne $fp.size)
    
    if ($needsDownload) {
        Write-Host "  Downloading: $($fp.filename)" -ForegroundColor Gray
        if (Download-File -Url $url -Destination $localFile) {
            $downloadCount.footprints++
        }
    }
}
Write-Success "Footprints: $($downloadCount.footprints) downloaded, $($libs.footprints.Count) total"

# 3D Models
Write-Info "Syncing 3D models..."
foreach ($model in $libs.'3dmodels') {
    $localFile = Join-Path $ModelsPath $model.filename
    $url = "$ServerUrl/kicad_libs/3dmodels/$($model.filename)"
    
    $needsDownload = $Force -or (-not (Test-Path $localFile)) -or ((Get-Item $localFile -ErrorAction SilentlyContinue).Length -ne $model.size)
    
    if ($needsDownload) {
        Write-Host "  Downloading: $($model.filename)" -ForegroundColor Gray
        if (Download-File -Url $url -Destination $localFile) {
            $downloadCount.models++
        }
    }
}
Write-Success "3D Models: $($downloadCount.models) downloaded, $($libs.'3dmodels'.Count) total"

# Update KiCad configuration
Write-Host ""
if ($kicadConfig) {
    Write-Info "Updating KiCad configuration..."
    
    # Update path variables
    Update-KiCadPaths -KiCadConfigPath $kicadConfig -SymbolsPath $SymbolsPath -FootprintsPath $FootprintsPath -ModelsPath $ModelsPath
    
    # Update symbol library table
    $newLibs = Update-SymLibTable -KiCadConfigPath $kicadConfig -SymbolsPath $SymbolsPath
}

# Mark as synced on server
Mark-ClientSynced

# Done
Write-Host ""
Write-Host "======================================" -ForegroundColor Green
Write-Host "  Sync Complete!" -ForegroundColor Green
Write-Host "======================================" -ForegroundColor Green
Write-Host ""
Write-Host "Downloaded: $($downloadCount.symbols) symbols, $($downloadCount.footprints) footprints, $($downloadCount.models) 3D models"
Write-Host "Symbols:    $SymbolsPath"
Write-Host "Footprints: $FootprintsPath"
Write-Host "3D Models:  $ModelsPath"
if ($kicadConfig) {
    Write-Host "KiCad config: $kicadConfig"
}
Write-Host ""
Write-Host "Note: Restart KiCad if it's currently running to see the new libraries." -ForegroundColor Yellow
Write-Host ""
