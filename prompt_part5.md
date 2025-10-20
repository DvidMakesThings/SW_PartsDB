Update README.md to fully satisfy §14–15 of prompt.md. Do NOT change code or layout.

REQUIREMENTS — README CONTENT
1) Quick start (no Docker)
   - Windows/PowerShell and Linux/macOS blocks:
     python -m venv .venv
     .\.venv\Scripts\activate    # (Windows)  |  source .venv/bin/activate  # (Unix)
     pip install -r backend/requirements.txt
     cd backend && python manage.py migrate && python manage.py runserver 0.0.0.0:8000
     # in another terminal
     cd frontend && npm i && npm run dev
   - Note default URLs: backend http://127.0.0.1:8000, frontend http://127.0.0.1:5173

2) Optional Docker path
   - docker compose up -d
   - First-time migrations and superuser:
     docker compose exec web python manage.py migrate
     docker compose exec web python manage.py createsuperuser

3) .env variables (document each; include defaults)
   - DATABASE_URL (default sqlite:///backend/partsdb.sqlite3)
   - MEDIA_ROOT (default backend/media)
   - DATASHEET_FETCH_ENABLED=true|false
   - REDIS_URL= (optional; if empty, datasheet fetch runs synchronously)
   - DJANGO_DEBUG=true
   - DJANGO_SECRET_KEY=change-me
   - VITE_API_BASE=http://127.0.0.1:8000

4) Folder conventions
   - backend/media/Datasheets/<Manufacturer>/<Category_L1>/<MPN>.pdf
   - backend/media/3D/<Package>/<Variant>/<MPN>.step
   - backend/media/Photos/<MPN>/front.jpg

5) CSV import — how-to
   - CLI:
     python backend/manage.py import_csv backend/tests/sample_components.csv --dry-run
     python backend/manage.py import_csv backend/tests/sample_components.csv
   - API:
     POST /api/import/csv (multipart: file=<csv>, dry_run=true|false)
   - Header map & normalization summary (from prompt.md §“CSV header map and parsing rules”)
   - Error logs saved under apps/inventory/import_errors/<timestamp>.csv

6) Datasheet fetch — how-to
   - Single: POST /api/components/{id}/fetch_datasheet/
   - Batch:  POST /api/components/fetch_missing_datasheets/
   - Sync fallback if REDIS_URL unset; files stored under Datasheets/…; SHA-256 dedupe; only PDFs.

7) OpenAPI, Admin & Health
   - Swagger UI:  /api/schema/swagger/
   - OpenAPI YAML: /api/schema/
   - Health:       /api/health
   - Admin:        /admin  (create superuser if needed)

8) Tests & quality
   - Run tests:  cd backend && pytest -q
   - Lint:       ruff check backend  (or flake8 if configured)
   - Formatting: ruff format backend  (if ruff formatter enabled)
   - Acceptance checklist (copy the ones from prompt.md and mark as passed)

9) Future notes (bullets)
   - Postgres migration (DATABASE_URL=postgres://…)
   - Barcode/QR support for InventoryItem
   - Bulk edits & CSV export
   - EAGLE ULP integration using /api/stock_check
   - CI with GitHub Actions
   - Optional Redis/Celery hardening

QUALITY BAR (apply now)
- Ensure README.md includes all items above with accurate commands for Windows and Unix.
- No TODOs. No placeholder text. Commands must be copy-paste runnable.

Deliverables
- README.md fully updated.
- If ruff is used, add a minimal ruff.toml at repo root with sane defaults (line-length=100, target-version="py310"); otherwise skip.
- Report the diff summary of README.md and any new config file (if added).
