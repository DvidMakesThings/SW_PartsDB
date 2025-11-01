Proceed with Step 2 and beyond per prompt.md. Use the existing repo and do NOT change the layout or rename files.

TASK A — Migrations + Health
1) Create and apply migrations for all models in apps: core, inventory, files, eagle.
2) Add health endpoint:
   - core/views.py: def health(request) -> JSON {"ok": true}
   - core/urls.py + project urls.py: mount GET /api/health
   - Return 200 always, no auth.

TASK B — API (DRF)
1) Create serializers and viewsets for:
   - inventory.Component
   - inventory.InventoryItem
   - files.Attachment
2) Routers:
   - /api/components/
   - /api/inventory/
   - /api/attachments/
3) Filters:
   - components: search on mpn, manufacturer, description; filters: manufacturer, category_l1, package_name, in_stock_only (bool).
4) Component actions:
   - POST /api/components/{id}/fetch_datasheet/  -> triggers fetch (sync if Celery absent).
   - POST /api/components/fetch_missing_datasheets/ -> scans all with url_datasheet set and no file.
5) OpenAPI + CORS:
   - Enable drf-spectacular; mount /api/schema/ and /api/schema/swagger/
   - Allow CORS from http://localhost:5173

TASK C — CSV Importer
1) Management command: backend/manage.py import_csv <path> [--dry-run] [--encoding=utf-8]
   - Map headers as in prompt.md.
   - Normalize manufacturer/mpn; upsert by (manufacturer_norm, mpn_norm).
   - Parse “Package (LxW)” and optional height to numeric mm.
   - Write bad rows to apps/inventory/import_errors/<timestamp>.csv
   - Print summary counts: created, updated, skipped, errors.
2) API endpoint: POST /api/import/csv (multipart form field 'file', optional 'dry_run')
   - Returns same summary JSON.

TASK D — Datasheet Fetcher
1) Service:
   - Download url_datasheet with requests (timeouts, follow redirects).
   - Accept only PDFs; verify bytes start with %PDF; compute SHA256; dedupe.
   - Save to MEDIA_ROOT/Datasheets/<Manufacturer>/<Category_L1>/<MPN>.pdf using files/services.py helpers.
   - Create/update files.Attachment(type='datasheet', sha256, source_url).
2) Celery:
   - Implement task files.tasks.fetch_datasheet(component_id).
   - If REDIS_URL unset, run synchronously from the API action (no Celery required).
3) Errors: return 400 with clear message on non-PDF/404; never crash.

TASK E — Admin polish
1) Components admin: list_display (mpn, manufacturer, category_l1, package_name), list_filter (manufacturer, category_l1, package_name), search_fields (mpn, manufacturer, description), action “Fetch datasheet”.
2) Inline attachments on Component detail.
3) Inventory admin: list_filter (storage_location, condition), search (component__mpn).

TASK F — Constraints & Normalization
1) Add UniqueConstraint on (manufacturer_normalized, mpn_normalized).
2) Model clean(): normalize mpn to uppercase ASCII, collapse whitespace/dashes; derive manufacturer_normalized similarly.
3) Ensure MEDIA_ROOT=backend/media exists on startup.

ACCEPTANCE CHECKS (run these; they must pass)
- python -m venv .venv && pip install -r backend/requirements.txt
- cd backend && python manage.py migrate && python manage.py runserver
- curl http://localhost:8000/api/health -> {"ok": true}
- python backend/manage.py import_csv backend/tests/sample_components.csv --dry-run
- python backend/manage.py import_csv backend/tests/sample_components.csv
- curl "http://localhost:8000/api/components/?search=SN65HVD11"
- POST /api/components/{id}/fetch_datasheet/ -> file saved under backend/media/Datasheets/...

Do not invent files. Do not skip steps. Keep code minimal, correct, and runnable.
