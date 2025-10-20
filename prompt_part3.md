Proceed with CSV importer and datasheet fetcher exactly per prompt.md. Do not change layout or names.

TASK 1 — CSV Importer
- Implement management command:
  python backend/manage.py import_csv <path> [--dry-run] [--encoding=utf-8] [--delimiter=,]
- Mapping + normalization as in prompt.md (parse "Package (LxW)", optional height; normalize manufacturer/mpn; upsert on (manufacturer_norm, mpn_norm)).
- On errors, write CSV to apps/inventory/import_errors/<timestamp>.csv with the original row plus an 'error' column.
- Print summary: created, updated, skipped, errors.
- Implement API endpoint:
  POST /api/import/csv  (multipart field 'file', optional 'dry_run': true/false)
  → return same summary JSON.

TASK 2 — Datasheet Fetcher
- Implement service that:
  * downloads url_datasheet (timeouts, redirects),
  * verifies PDF (Content-Type AND bytes start with %PDF),
  * computes SHA256 and dedupes,
  * saves to MEDIA_ROOT/Datasheets/<Manufacturer>/<Category_L1>/<MPN>.pdf using files/services.py helpers,
  * creates/updates files.Attachment(type='datasheet', sha256, source_url).
- Implement Celery task files.tasks.fetch_datasheet(component_id).
- API actions on ComponentViewSet:
  * POST /api/components/{id}/fetch_datasheet/
  * POST /api/components/fetch_missing_datasheets/
- If REDIS_URL absent, actions must run the same logic synchronously (no Celery required).

TASK 3 — Filters polish
- Components list supports:
  * search on mpn, manufacturer, description
  * filters: manufacturer, category_l1, package_name, in_stock_only (bool: component has any InventoryItem with qty > 0)

After implementing, run these acceptance checks:

1) Dry-run import:
   python backend/manage.py import_csv backend/tests/sample_components.csv --dry-run

2) Real import:
   python backend/manage.py import_csv backend/tests/sample_components.csv

3) API import (multipart):
   # PowerShell example
   Invoke-WebRequest -Method POST `
     -Uri http://127.0.0.1:8000/api/import/csv `
     -Form @{ file = Get-Item "backend/tests/sample_components.csv"; dry_run = "false" }

4) Search endpoint:
   curl "http://127.0.0.1:8000/api/components/?search=SN65HVD11"

5) Datasheet fetch single component (replace {id}):
   curl -X POST http://127.0.0.1:8000/api/components/{id}/fetch_datasheet/

6) Verify file saved under backend/media/Datasheets/... and Attachment row exists.

Report changed files and the test outputs. Do not invent new files or endpoints.
