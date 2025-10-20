# Add inventory items for existing components in PartsDB
$root = "G:\_GitHub\SW_PartsDB"
$venv = "$root\.venv"

Write-Host "=== PartsDB Inventory Addition Script ===" -ForegroundColor Cyan

# Activate virtual environment
Write-Host "Activating virtual environment..." -ForegroundColor Yellow
& "$venv\Scripts\Activate.ps1"

# Check if Django is running
try {
    $test = Invoke-WebRequest -Uri "http://localhost:8000/api/components/" -Method HEAD -UseBasicParsing -ErrorAction SilentlyContinue
    if ($test.StatusCode -ne 200) {
        Write-Host "Django API is not responding. Please make sure the backend is running." -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "Django API is not responding. Please make sure the backend is running." -ForegroundColor Red
    exit 1
}

# Get existing components
Write-Host "Fetching components from API..." -ForegroundColor Yellow
$response = Invoke-WebRequest -Uri "http://localhost:8000/api/components/" -UseBasicParsing
$components = ($response.Content | ConvertFrom-Json).results

# Check if we got components
$total = $components.Count
if ($total -eq 0) {
    Write-Host "No components found in the database. Please import components first." -ForegroundColor Red
    exit 1
}

Write-Host "Found $total components. Adding sample inventory items..." -ForegroundColor Green

# Sample locations for inventory
$locations = @(
    "Main Storage A1",
    "Main Storage B2", 
    "Main Storage C3",
    "Secondary Storage D4",
    "Project Box Alpha",
    "Project Box Beta",
    "Prototyping Drawer",
    "Emergency Stock"
)

# Add inventory items for some components (not all)
$counter = 0
$numToAdd = [Math]::Min(20, $total)
$success = 0
$errors = 0

# Seed random number generator
$random = New-Object System.Random

foreach ($component in $components | Select-Object -First $numToAdd) {
    $counter++
    Write-Progress -Activity "Adding Inventory Items" -Status "Processing $counter of $numToAdd" -PercentComplete (($counter / $numToAdd) * 100)
    
    # Random quantity between 1 and 50
    $quantity = $random.Next(1, 51)
    
    # Random location
    $location = $locations[$random.Next(0, $locations.Count)]
    
    # Create inventory JSON
    $inventoryData = @{
        component = $component.id
        storage_location = $location
        quantity = $quantity
        notes = "Sample inventory added for testing"
    }
    
    # Convert to JSON
    $json = $inventoryData | ConvertTo-Json
    
    try {
        # Send to API
        $response = Invoke-RestMethod -Uri "http://localhost:8000/api/inventory/" -Method Post -Body $json -ContentType "application/json" -UseBasicParsing
        Write-Host "  Added $quantity of $($component.mpn) at $location" -ForegroundColor Green
        $success++
        
        # Add a second inventory item for some components
        if ($random.Next(0, 2) -eq 1) {
            $quantity2 = $random.Next(1, 26)
            $location2 = $locations[$random.Next(0, $locations.Count)]
            while ($location2 -eq $location) {
                $location2 = $locations[$random.Next(0, $locations.Count)]
            }
            
            $inventoryData2 = @{
                component = $component.id
                storage_location = $location2
                quantity = $quantity2
                notes = "Additional inventory for testing"
            }
            
            $json2 = $inventoryData2 | ConvertTo-Json
            
            $response2 = Invoke-RestMethod -Uri "http://localhost:8000/api/inventory/" -Method Post -Body $json2 -ContentType "application/json" -UseBasicParsing
            Write-Host "    Also added $quantity2 of $($component.mpn) at $location2" -ForegroundColor Cyan
            $success++
        }
    } catch {
        Write-Host "  Error adding inventory for $($component.mpn): $($_.Exception.Message)" -ForegroundColor Red
        $errors++
    }
}

# Final report
Write-Host "`n=== Inventory Addition Complete ===" -ForegroundColor Cyan
Write-Host "Successfully added: $success inventory items" -ForegroundColor Green
Write-Host "Errors: $errors" -ForegroundColor $(if($errors -gt 0){[System.ConsoleColor]::Red}else{[System.ConsoleColor]::Green})

Write-Host "`nYou can now refresh the Inventory page in the browser to see the added items." -ForegroundColor Cyan