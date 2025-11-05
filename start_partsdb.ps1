# One-click startup for PartsDB (PowerShell)
$root = "G:\_GitHub\SW_PartsDB"
$backend = "$root\partsdb\backend"
$frontend = "$root\partsdb\frontend"
$venv = "$root\.venv"

Write-Host "=== PartsDB Startup Script ===" -ForegroundColor Cyan

# Kill any existing processes on the ports we want to use
Write-Host "Stopping any existing processes on ports 8000, 5173, 5174, 5175..." -ForegroundColor Yellow
Get-Process | Where-Object { $_.ProcessName -like "*node*" } | Stop-Process -Force -ErrorAction SilentlyContinue
$runningProcesses = Get-NetTCPConnection -LocalPort 8000, 5173, 5174, 5175 -ErrorAction SilentlyContinue | 
                    Select-Object -ExpandProperty OwningProcess | 
                    Sort-Object -Unique

foreach ($process in $runningProcesses) {
    try {
        $p = Get-Process -Id $process -ErrorAction SilentlyContinue
        if ($p) {
            Write-Host "Stopping process $($p.Name) (PID: $process)" -ForegroundColor Yellow
            Stop-Process -Id $process -Force
        }
    } catch {
        Write-Host "Could not stop process with ID $process" -ForegroundColor Red
    }
}

# Check if index.html exists and create if not
$indexPath = "$frontend\index.html"
if (-not (Test-Path $indexPath)) {
    Write-Host "Creating index.html in frontend directory..." -ForegroundColor Yellow
    $indexHtml = @"
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="/favicon.ico" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Parts DB</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
"@
    $indexHtml | Out-File -FilePath $indexPath -Encoding utf8
    Write-Host "  Created index.html at: $indexPath" -ForegroundColor Green
}

# Ensure main.tsx is pointing to the correct CSS file
$mainTsxPath = "$frontend\src\main.tsx"
if (Test-Path $mainTsxPath) {
    $mainTsxContent = Get-Content -Path $mainTsxPath -Raw
    if ($mainTsxContent -match "import './styles/index.css'") {
        Write-Host "Fixing CSS import path in main.tsx..." -ForegroundColor Yellow
        $mainTsxContent = $mainTsxContent -replace "import './styles/index.css'", "import './index.css'"
        $mainTsxContent | Out-File -FilePath $mainTsxPath -Encoding utf8
        Write-Host "  Fixed CSS import path" -ForegroundColor Green
    }
}

# Activate virtual environment
Write-Host "Setting up Python virtual environment..." -ForegroundColor Cyan
if (Test-Path "$venv\Scripts\Activate.ps1") {
    & "$venv\Scripts\Activate.ps1"
} else {
    Write-Host "Creating new virtual environment..." -ForegroundColor Yellow
    python -m venv "$venv"
    & "$venv\Scripts\Activate.ps1"
    
    Write-Host "Installing backend dependencies..." -ForegroundColor Yellow
    pip install -r "$backend\requirements.txt"
}

# Make sure frontend dependencies are installed
Write-Host "Checking frontend dependencies..." -ForegroundColor Cyan
if (-not (Test-Path "$frontend\node_modules")) {
    Write-Host "Installing frontend dependencies..." -ForegroundColor Yellow
    Push-Location $frontend
    npm install
    Pop-Location
    Write-Host "  Frontend dependencies installed" -ForegroundColor Green
} else {
    Write-Host "  Frontend dependencies already installed" -ForegroundColor Green
}

# Start backend
Write-Host "Starting Django backend server..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd `"$backend`"; & `"$venv\Scripts\Activate.ps1`"; python manage.py migrate; python manage.py runserver 0.0.0.0:8000" -WindowStyle Normal

# Wait a moment for the backend to start
Start-Sleep -Seconds 3

# Start frontend
Write-Host "Starting React frontend server..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd `"$frontend`"; npm run dev" -WindowStyle Normal

# Wait to check if the frontend started successfully
Start-Sleep -Seconds 5

# Check if servers are running
$backendRunning = $false
$frontendRunning = $false

try {
    $backend = Invoke-WebRequest -Uri "http://localhost:8000/api/components/" -Method HEAD -UseBasicParsing -ErrorAction SilentlyContinue
    if ($backend.StatusCode -eq 200) {
        $backendRunning = $true
    }
} catch {}

try {
    $frontend = Invoke-WebRequest -Uri "http://localhost:5173/" -Method HEAD -UseBasicParsing -ErrorAction SilentlyContinue
    if ($frontend.StatusCode -eq 200) {
        $frontendRunning = $true
    }
} catch {}

Write-Host "`n=== Status Report ===" -ForegroundColor Cyan
Write-Host "Backend API: $(if($backendRunning){"✅ Running"}else{"❌ Not responding"})" -ForegroundColor $(if($backendRunning){[System.ConsoleColor]::Green}else{[System.ConsoleColor]::Red})
Write-Host "Frontend: $(if($frontendRunning){"✅ Running"}else{"❌ Not responding"})" -ForegroundColor $(if($frontendRunning){[System.ConsoleColor]::Green}else{[System.ConsoleColor]::Red})

Write-Host "`n=== Access URLs ===" -ForegroundColor Cyan
Write-Host "Backend API: http://localhost:8000/api" -ForegroundColor Green
Write-Host "Frontend: http://localhost:5173" -ForegroundColor Green

# Get a network IP address for access from other devices
$networkIp = (Get-NetIPAddress -AddressFamily IPv4).Where{
    $_.InterfaceAlias -notmatch 'Loopback|VMware|WSL|vEthernet' -and
    $_.PrefixLength -lt 32
} | Sort-Object InterfaceIndex | Select-Object -First 1 -ExpandProperty IPAddress

if ($networkIp) {
    Write-Host "External access: http://${networkIp}:5173" -ForegroundColor Green
}

if (-not $backendRunning -or -not $frontendRunning) {
    Write-Host "`n⚠️ TROUBLESHOOTING TIPS ⚠️" -ForegroundColor Yellow
    
    if (-not $backendRunning) {
        Write-Host "  Backend issues:" -ForegroundColor Yellow
        Write-Host "  - Check if Django is installed and requirements are met" -ForegroundColor Yellow
        Write-Host "  - Look for error messages in the backend terminal" -ForegroundColor Yellow
        Write-Host "  - Try running 'python manage.py runserver 0.0.0.0:8000' manually" -ForegroundColor Yellow
    }
    
    if (-not $frontendRunning) {
        Write-Host "  Frontend issues:" -ForegroundColor Yellow
        Write-Host "  - Verify index.html exists at: $indexPath" -ForegroundColor Yellow
        Write-Host "  - Check for TypeScript or build errors in the frontend terminal" -ForegroundColor Yellow
        Write-Host "  - Try running 'npm run dev' manually in the frontend directory" -ForegroundColor Yellow
        Write-Host "  - Try accessing http://localhost:5173/index.html directly" -ForegroundColor Yellow
    }
    
    Write-Host "  General fixes:" -ForegroundColor Yellow
    Write-Host "  - Make sure ports 8000 and 5173 are not in use by other applications" -ForegroundColor Yellow
    Write-Host "  - Try restarting your computer if the problem persists" -ForegroundColor Yellow
}
