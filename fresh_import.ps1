# Fresh database import script for Windows PowerShell

Write-Host "Deleting existing database..." -ForegroundColor Yellow
Remove-Item -Path "partsdb/backend/db.sqlite3" -Force -ErrorAction SilentlyContinue

Write-Host "Running migrations..." -ForegroundColor Cyan
Set-Location partsdb/backend
python manage.py migrate

Write-Host "`nImporting components from CSV..." -ForegroundColor Cyan
python manage.py import_csv ../_csv_renderer/DMT_Partslib.csv

Write-Host "`nChecking results..." -ForegroundColor Cyan
python -c "import os,django; os.environ.setdefault('DJANGO_SETTINGS_MODULE','partsdb.settings'); django.setup(); from apps.inventory.models import Component; print(f'Total components: {Component.objects.count()}'); print(f'With DMT codes: {Component.objects.exclude(dmtuid__isnull=True).count()}')"

Write-Host "`nDone! You can now run:" -ForegroundColor Green
Write-Host "  python manage.py runserver" -ForegroundColor White
