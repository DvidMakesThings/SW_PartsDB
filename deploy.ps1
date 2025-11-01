# PartsDB Deployment Script for Windows
# This script builds Docker images and starts the PartsDB application

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  PartsDB Deployment Script (Windows)" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check if Docker is installed
Write-Host "Checking Docker installation..." -ForegroundColor Yellow
try {
    $dockerVersion = docker --version
    Write-Host "✓ Docker found: $dockerVersion" -ForegroundColor Green
} catch {
    Write-Host "✗ Docker is not installed or not in PATH" -ForegroundColor Red
    Write-Host "Please install Docker Desktop from: https://www.docker.com/products/docker-desktop" -ForegroundColor Red
    exit 1
}

# Check if Docker is running
Write-Host "Checking if Docker is running..." -ForegroundColor Yellow
try {
    docker ps | Out-Null
    Write-Host "✓ Docker is running" -ForegroundColor Green
} catch {
    Write-Host "✗ Docker is not running" -ForegroundColor Red
    Write-Host "Please start Docker Desktop and try again" -ForegroundColor Red
    exit 1
}

# Navigate to partsdb directory
$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location "$scriptPath\partsdb"

Write-Host ""
Write-Host "Building Docker images..." -ForegroundColor Yellow
Write-Host "This may take several minutes on first run..." -ForegroundColor Gray
Write-Host ""

# Build images using docker-compose
docker-compose build

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "✗ Failed to build Docker images" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "✓ Docker images built successfully" -ForegroundColor Green
Write-Host ""

# Stop any existing containers
Write-Host "Stopping any existing containers..." -ForegroundColor Yellow
docker-compose down

# Start the application
Write-Host ""
Write-Host "Starting PartsDB application..." -ForegroundColor Yellow
docker-compose up -d

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "✗ Failed to start containers" -ForegroundColor Red
    exit 1
}

# Wait for services to initialize
Write-Host ""
Write-Host "Waiting for services to initialize..." -ForegroundColor Yellow
Start-Sleep -Seconds 5

# Run database migrations
Write-Host "Running database migrations..." -ForegroundColor Yellow
docker-compose exec -T backend python manage.py migrate

if ($LASTEXITCODE -ne 0) {
    Write-Host "⚠ Warning: Database migrations may have failed" -ForegroundColor Yellow
    Write-Host "You may need to run migrations manually:" -ForegroundColor Yellow
    Write-Host "  docker-compose exec backend python manage.py migrate" -ForegroundColor Gray
}

# Check service status
Write-Host ""
Write-Host "Checking service status..." -ForegroundColor Yellow
Write-Host ""
docker-compose ps

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  PartsDB is now running!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Access the application at:" -ForegroundColor Cyan
Write-Host "  Frontend: http://localhost:5173" -ForegroundColor White
Write-Host "  Backend:  http://localhost:8000" -ForegroundColor White
Write-Host "  API Docs: http://localhost:8000/api/schema/swagger-ui/" -ForegroundColor White
Write-Host ""
Write-Host "Useful commands:" -ForegroundColor Cyan
Write-Host "  View logs:         docker-compose logs -f" -ForegroundColor Gray
Write-Host "  Stop application:  docker-compose down" -ForegroundColor Gray
Write-Host "  Restart:           docker-compose restart" -ForegroundColor Gray
Write-Host "  Create admin:      docker-compose exec backend python manage.py createsuperuser" -ForegroundColor Gray
Write-Host ""
Write-Host "Press Ctrl+C to exit (containers will continue running)" -ForegroundColor Yellow
Write-Host ""
