You are generating a complete, production-ready project named **partsdb**.
Stack: **Python 3.10+**, **Django 5 + Django REST Framework**, **PostgreSQL or SQLite** (dev uses SQLite by default), **Celery + Redis** for background jobs, **React + Vite + TypeScript + Tailwind** for the UI. Provide a Docker setup as an optional convenience, but the project must also run locally without Docker.

# Generation order and hard checks

1. Scaffold backend, install deps, create Django project and apps exactly as in layout.
2. Implement models, migrations, admin. Run `makemigrations` and `migrate`.
3. Wire DRF routers and CORS. Add healthcheck at `GET /api/health` → `{"ok":true}`.
4. Implement CSV importer CLI + API. Prove with a sample CSV in repo.
5. Implement file saving service with deterministic paths under `MEDIA_ROOT`.
6. Implement datasheet fetcher with synchronous fallback if Celery/Redis is absent.
7. Implement React UI pages and API client.
8. Run pytest. All tests green.
9. Update README quick start and verify the app runs with SQLite and without Docker.

# Acceptance tests Copilot must satisfy

* `python -m venv .venv && pip install -r backend/requirements.txt && cd backend && python manage.py migrate && python manage.py runserver` starts without error.
* `curl http://localhost:8000/api/health` returns `{"ok":true}`.
* `python backend/manage.py import_csv backend/tests/sample_components.csv --dry-run` prints a summary.
* `python backend/manage.py import_csv backend/tests/sample_components.csv` creates rows.
* `POST /api/components/?search=SN65HVD11` returns the component.
* `POST /api/components/{id}/fetch_datasheet/` stores a PDF under `backend/media/Datasheets/...`.
* Frontend `npm i && npm run dev` starts and lists components without errors.

## 1) Monorepo layout (exact paths)

```
partsdb/
  README.md
  .env.example
  docker-compose.yml
  Makefile
  scripts/
    dev_run.bat
    dev_run.sh
  backend/
    manage.py
    pyproject.toml
    requirements.txt
    partsdb/                # Django project
      __init__.py
      settings.py
      urls.py
      asgi.py
      celery.py
    apps/
      core/                 # shared utils, enums, mixins
      inventory/            # main app with models, API, importers
      files/                # file storage, attachments
      eagle/                # future: EAGLE integration endpoints
    media/                  # file storage root (datasheets, 3D, photos)
      Datasheets/<Mfr>/<CatL1>/<MPN>.pdf
      3D/<Package>/<Variant>/<MPN>.step
      Photos/<MPN>/front.jpg
    tests/
      pytest.ini
      api/                  # API tests
      importers/            # CSV importer tests
  frontend/
    index.html
    package.json
    vite.config.ts
    src/
      main.tsx
      App.tsx
      api/                  # typed API client
      components/
      pages/
        Components.tsx
        ComponentDetail.tsx
        Inventory.tsx
        ImportCsv.tsx
        Attachments.tsx
      styles/
```

## 2) Python env & dependencies

Backend uses:

* `Django==5.*`, `djangorestframework`, `django-filter`, `python-dotenv`
* `psycopg[binary]` (optional), otherwise SQLite default
* `celery`, `redis` (optional for background downloads; if Redis not running, fallback to synchronous)
* `pydantic` for config, `requests` for datasheet fetch
* `pytest`, `pytest-django`, `factory-boy` for tests

Add `Makefile` tasks: `make dev`, `make migrate`, `make test`, `make superuser`.

## 3) Settings

* Read config from `.env` with defaults:

  * `DATABASE_URL` (default SQLite: `sqlite:///backend/partsdb.sqlite3`)
  * `MEDIA_ROOT=backend/media`
  * `DATASHEET_FETCH_ENABLED=true`
  * `REDIS_URL=redis://localhost:6379/0` (optional)
* Static/media served in dev; production assumes reverse proxy.

## 4) Data model (Django models, DRF serializers)

**inventory.Component** (unique by `manufacturer` + `mpn`)

* `id` (UUID PK)
* `mpn` (Char, indexed, uppercase normalized)
* `manufacturer` (Char)
* `value` (Char), `tolerance` (Char)
* `wattage` (Char), `voltage` (Char), `current` (Char)
* `package_name` (Char)  — human string e.g. “SOIC-8”
* `package_l_mm` (Decimal, null), `package_w_mm` (Decimal, null), `package_h_mm` (Decimal, null), `pins` (Integer, null), `pitch_mm` (Decimal, null)
* `description` (Text)
* `lifecycle` (Choice: ACTIVE/NRND/EOL/UNKNOWN)
* `rohs` (Boolean, null)
* `temp_grade` (Char, null)
* `url_datasheet` (URL, null)
* `url_alt` (URL, null)
* `category_l1` (Char, default="Unsorted")
* `category_l2` (Char, null)
* `footprint_name` (Char, null)      # must match your EAGLE lib device name
* `step_model_path` (Char, null)     # repo-relative path to STEP
* `created_at`, `updated_at` (auto)

**inventory.InventoryItem**

* `id` (UUID PK)
* `component` (FK → Component, cascade)
* `quantity` (Integer)
* `uom` (Char: pcs/reel/tube/tray)
* `storage_location` (Char)          # “Rack A / Box C3”
* `lot_code` (Char, null), `date_code` (Char, null)
* `supplier` (Char, null), `price_each` (Decimal, null)
* `condition` (Char: new/used/expired)
* `note` (Text, null)
* timestamps

**files.Attachment**

* `id` (UUID PK)
* `component` (FK → Component, cascade)
* `type` (Choice: datasheet/three_d/photo/appnote/other)
* `file` (FileField)  # stored under MEDIA_ROOT with deterministic subpaths (see 6)
* `source_url` (URL, null)
* `sha256` (Char(64), indexed, null)
* timestamps

**eagle.EagleLink** (placeholder for future integration)

* `component` (FK)
* `eagle_library` (Char)
* `eagle_device` (Char)
* `eagle_package` (Char)
* `notes` (Text)

Add model clean() methods to normalize `mpn` to uppercase, strip spaces/dashes, and to dedupe size parsing from “Package (LxW)” when importing.

## 5) CSV Importer

Create an importer view and management command that ingests a CSV like the user’s (columns may include: `MPN, Value, Tolerance, Wattage, Voltage, Current, Dielectric Characteristic, Resistance, Impedance, Package (LxW), Description, Manufacturer, Datasheet`). Rules:

* Map arbitrary column names to model fields via a **field map**. Unknown columns go into a JSON `extras` dict (Optional field on Component if you add one).
* Split “Package (LxW)” like “12.00mm x 12.00mm” into L/W; if a height appears elsewhere (“Height - after installation (max.)”), parse to `package_h_mm`.
* De-dupe by `(manufacturer_normalized, mpn_normalized)`. If exists, update non-empty fields.
* Create/append an `InventoryItem` with `quantity` if CSV has qty, else skip.
* Category auto-assignment: use keyword rules (see #10). Allow manual override later.
* Option: dry-run mode with a diff summary.
* Log rows with errors to `backend/apps/inventory/import_errors/YYYYMMDD_HHMM.csv`.

Expose:

* `POST /api/import/csv` (multipart) → returns summary: created, updated, skipped, errors.
* `python backend/manage.py import_csv path/to/file.csv --dry-run` for CLI.

## 6) File storage and naming

Store files under `MEDIA_ROOT` with deterministic paths:

* Datasheets: `Datasheets/<Manufacturer>/<Category_L1>/<MPN>.pdf`
* 3D models: `3D/<Package>/<Variant>/<MPN>.step`
* Photos: `Photos/<MPN>/front.jpg`

**files.services**: write a helper that, given `component` + `type` + `source_url` + file bytes, returns a safe relative path, saves file, computes SHA-256, and dedupes if a matching hash already exists.

## 7) Datasheet downloader (Celery task)

* Task: `files.tasks.fetch_datasheet(component_id)`
* Fetch `url_datasheet` via `requests` with user-agent, 15 s timeout, follow redirects, only accept `content-type=application/pdf`.
* Save to deterministic path. Update or create `Attachment(type='datasheet')`.
* If `REDIS_URL` not set, run synchronously (simple function call).
* Expose API:

  * `POST /api/components/{id}/fetch_datasheet/` to enqueue
  * `POST /api/components/fetch_missing_datasheets/` to enqueue for all with URL but no file

## 8) REST API (DRF)

Endpoints (paginated, filterable):

* `GET/POST /api/components/`
* `GET/PATCH /api/components/{id}/`
* Filters: `search=`, `manufacturer=`, `category_l1=`, `package_name=`, `has_stock` (bool), `in_stock_only`
* `GET/POST /api/inventory/` and `/api/inventory/{id}/`
* `GET/POST /api/attachments/` and `/api/attachments/{id}/`
* Actions: `components/{id}/fetch_datasheet/` (see 7)
* Import: `POST /api/import/csv`
* “Stock check”: `POST /api/components/check_stock` with list of `{manufacturer, mpn}` returns in-stock quantities (future EAGLE hook)

Enable CORS for `http://localhost:5173`.

## 9) Admin UI (Django admin)

* Register `Component`, `InventoryItem`, `Attachment` with list filters (manufacturer, category_l1, package, in-stock).
* Inline attachments on Component detail.
* Action: “Fetch datasheet for selected”.

## 10) Category taxonomy (auto rules)

Implement a rules engine in `inventory/categorizer.py`:

* Regex/keyword → `(category_l1, category_l2)` pairs. Examples:

  * “Transceiver|RS-485|485” → Interface / RS-485
  * “CANFD|CAN-FD|TJA1100|PHY|88E1512” → Interface / Ethernet
  * “Op Amp|OPA\d+|LMV|LM3\d+” → Analog / Op-Amps
  * “MOSFET|PowerPAK|2N7002|BSS138|SiR” → Power / MOSFETs
  * “LDO|Regulator|TPS7|LM2940|LM2937|TPS74801” → Power / LDO
  * “Buck|Step-Down|TPS57|LM2670|NCV6323” → Power / Buck
  * “Boost|Step-Up|TPS6102” → Power / Boost
  * “EEPROM|Flash|Winbond|Micron|N25Q|M95256” → Memory / SPI NOR & EEPROM
  * “Ferrite Bead|BLM|MPZ|7427” → EMC / Ferrite Beads
  * “TVS|ESD|PESD|RClamp|Zener” → Protection / ESD & TVS
  * “Inductor|WE-PD|XAL|SRP|IHLP|74477” → Passives / Inductors
  * “Resistor|Shunt|Isabellenhütte|SMS-R|ERJ|RT1206” → Passives / Resistors
  * “Capacitor|MLCC|X7R|C0G|Murata|TDK|Kemet|AVX” → Passives / Capacitors
* Provide a YAML file `backend/apps/inventory/category_rules.yaml` loaded at startup so the user can edit rules without code changes.

## 11) Frontend (React + Vite + TS + Tailwind)

Pages:

* **Components list**: table with search, filters (facets), columns: MPN, Manufacturer, Value, Package, Category, In-stock.
* **Component detail**: tabs “Overview”, “Inventory”, “Attachments”. Buttons: “Fetch datasheet”, “Add inventory item”, “Upload 3D”, “Upload photo”.
* **Inventory view**: show all reels/bags, editable quantity, location.
* **CSV Import**: upload CSV, dry-run checkbox, results table (created/updated/errors).
* Show a link to open component datasheet (if downloaded) or the source URL.

Use a tiny API client with Axios, typed DTOs.

## 12) EAGLE integration placeholders

* Add endpoint `POST /api/stock_check` with payload: `[{manufacturer, mpn, quantity_needed}]` returning `[{mpn, have, need, ok}]`.
* Add endpoint `GET /api/components/by_mpn?mpn=...&manufacturer=...`
* Document in README how EAGLE ULP can call these (HTTP GET/POST) and how schematic `Attributes` should carry `MPN`, `MANUFACTURER`, `FOOTPRINT`.

## 13) Tests (pytest)

* Importer test: feed a sample CSV with the user’s columns; assert components created, size parsed, de-dupe works.
* Datasheet fetcher test: mock requests, verify file saved, SHA256 computed, duplicate prevented.
* API tests: list/filter/search, create inventory item, attachments upload.
* Categorizer test: map representative MPNs to expected categories.

## 14) README (must include)

* Quick start (no Docker): `python -m venv`, `pip install -r requirements.txt`, `python manage.py migrate`, `python manage.py runserver`, `npm i && npm run dev` for frontend.
* Optional Docker path with `docker-compose up`.
* .env variables explained.
* Folder conventions for **Datasheets**, **3D**, **Photos**.
* How CSV import works, sample header map.
* How to enable/disable Celery; synchronous fallback if Redis absent.
* Notes for future: PostgreSQL migration, auth/permissions, barcode/QR support, bulk edits.

## 15) Quality bar

* Generate all code with correct imports, migrations, serializers, routers, CORS config, and working UI.
* Run `flake8` or `ruff` and fix obvious lint.
* No dead TODOs. Ship something that starts and passes tests out-of-the-box.

# Implementation constraints

* Do not invent folders outside the specified layout.
* Pin versions in `backend/requirements.txt` to latest stable known to work with Django 5 and DRF.
* Use SQLite by default. If `DATABASE_URL` is unset, connect to `sqlite:///backend/partsdb.sqlite3`.
* `MEDIA_ROOT` must be `backend/media` relative to repo root. Create dirs on startup if missing.
* File uploads: max 20 MB, accept only `application/pdf` for datasheets.
* Normalize MPN: uppercase, strip spaces and unicode dashes to ASCII hyphen. Use this normalized value for uniqueness.
* Importer must tolerate missing columns and extra columns.
* If `REDIS_URL` is not set, Celery is not required. The datasheet fetch API must still work synchronously.
* Provide an OpenAPI schema at `/api/schema/` and `/api/schema/swagger/`.
* No example code left commented-out. No TODOs. Everything runnable.

# Exact dependency pins (backend/requirements.txt)

```
Django==5.1.2
djangorestframework==3.15.2
django-filter==24.3
python-dotenv==1.0.1
pydantic==2.9.2
requests==2.32.3
drf-spectacular==0.27.2
celery==5.4.0
redis==5.0.8
psycopg[binary]==3.2.1
pytest==8.3.2
pytest-django==4.8.0
factory-boy==3.3.0
```

# Makefile targets

```
.PHONY: dev migrate superuser test fmt lint seed
dev:        ## run backend dev server
\tcd backend && python manage.py runserver 0.0.0.0:8000
migrate:
\tcd backend && python manage.py makemigrations && python manage.py migrate
superuser:
\tcd backend && python manage.py createsuperuser
test:
\tcd backend && pytest -q
```

# Settings must-do (backend/partsdb/settings.py)

* Read `.env`.
* CORS allow `http://localhost:5173`.
* `MEDIA_ROOT = BASE_DIR / "media"` and `MEDIA_URL = "/media/"`.
* DRF default pagination size 50.
* drf-spectacular enabled and mounted at `/api/schema/` and `/api/schema/swagger/`.

# Deterministic file paths

Write `files/services.py` with:

```
def datasheet_relpath(manufacturer:str, cat_l1:str, mpn:str) -> Path:
    return Path("Datasheets")/safe(manufacturer)/safe(cat_l1 or "Unsorted")/(safe(mpn)+".pdf")
def step_relpath(package:str, variant:str, mpn:str) -> Path:
    return Path("3D")/safe(package or "Unknown")/safe(variant or "Generic")/(safe(mpn)+".step")
def photo_relpath(mpn:str) -> Path:
    return Path("Photos")/safe(mpn)/"front.jpg"
```

`safe()` replaces spaces with `_`, strips path separators, and normalizes unicode.

# CSV header map and parsing rules

Accept any of these headers and map to model fields:

```
"MPN"->mpn, "Manufacturer"->manufacturer, "Value"->value, "Tolerance"->tolerance,
"Wattage"->wattage, "Voltage"->voltage, "Current"->current,
"Description"->description, "Datasheet"->url_datasheet,
"Package (LxW)"->package_l_mm/package_w_mm (parse "12.00mm x 12.00mm"),
"Height - after installation (max.)"->package_h_mm,
"Resistance"->extras.resistance, "Impedance"->extras.impedance
```

De-dupe on `(manufacturer_normalized, mpn_normalized)`. If existing row has empty fields and CSV has data, fill them. If both non-empty and different, keep existing but log to `import_errors`.

# Category rules starter (backend/apps/inventory/category_rules.yaml)

```
rules:
  - pattern: "(?i)RS-485|SN65HVD"
    l1: "Interface"
    l2: "RS-485"
  - pattern: "(?i)CAN-?FD|TJA1100|PHY|88E1512|Ethernet"
    l1: "Interface"
    l2: "Ethernet"
  - pattern: "(?i)Op.?Amp|OPA\\d+|LM50|OPA365"
    l1: "Analog"
    l2: "Op-Amps & Sensors"
  - pattern: "(?i)Buck|Step-Down|TPS57|LM2670|NCV6323"
    l1: "Power"
    l2: "Buck Converters"
  - pattern: "(?i)Boost|Step-Up|TPS6102"
    l1: "Power"
    l2: "Boost Converters"
  - pattern: "(?i)LDO|Regulator|LM2937|LM3940|TPS74801"
    l1: "Power"
    l2: "LDO Regulators"
  - pattern: "(?i)EEPROM|Flash|Winbond|Micron|N25Q|M95256"
    l1: "Memory"
    l2: "SPI NOR & EEPROM"
  - pattern: "(?i)Ferrite Bead|BLM|MPZ|7427"
    l1: "EMC"
    l2: "Ferrite Beads"
  - pattern: "(?i)TVS|ESD|PESD|RClamp|Zener"
    l1: "Protection"
    l2: "ESD & TVS"
  - pattern: "(?i)Inductor|WE-PD|XAL|SRP|IHLP|74477"
    l1: "Passives"
    l2: "Inductors"
  - pattern: "(?i)Resistor|Shunt|Isabellenhütte|SMS-R|ERJ|RT1206"
    l1: "Passives"
    l2: "Resistors"
  - pattern: "(?i)Capacitor|MLCC|X7R|C0G|Murata|TDK|Kemet|AVX|Kyocera"
    l1: "Passives"
    l2: "Capacitors"
fallback:
  l1: "Unsorted"
  l2: null
```

# Synchronous fallback for datasheet fetch

If Celery is unavailable, `POST /api/components/{id}/fetch_datasheet/` must call the same function inline and return `{"saved": true, "path": ".../Datasheets/...pdf"}`. Do not crash if content-type is not PDF. Return a 400 with a clear message.

# OpenAPI contract (drf-spectacular)

Document:

* `GET /api/components/` list with filters `search`, `manufacturer`, `category_l1`, `in_stock_only`.
* `POST /api/import/csv` multipart with field `file` and boolean `dry_run`.
* Actions:

  * `POST /api/components/{id}/fetch_datasheet/`
  * `POST /api/components/fetch_missing_datasheets/`
* `POST /api/components/check_stock` request body `[{manufacturer, mpn, quantity_needed}]` returns `[{mpn, have, need, ok}]`.

# Seed files to include in repo

* `backend/tests/sample_components.csv` small realistic sample with your headers.
* `backend/apps/inventory/category_rules.yaml` from above.
* `backend/tests/__snapshots__/` left empty but present.
* `frontend/src/api/types.ts` with DTOs matching the serializers.

Sample CSV row:

```
MPN,Manufacturer,Value,Tolerance,Wattage,Voltage,Current,Package (LxW),Description,Datasheet
7447709100,Würth Elektronik,10uH,20%,,,"7.1A","12.00mm x 12.00mm","WE-PD Inductor","https://www.we-online.com/components/products/datasheet/7447709100.pdf"
88E1512-A0-NNP2I000,Marvell,,,"",,,"QFN-56","Gigabit Ethernet PHY","https://www.marvell.com/.../88e151x-datasheet.pdf"
SN65HVD11DR,Texas Instruments,,,,,,SOIC-8,"3.3-V RS-485 Transceiver","https://www.ti.com/lit/ds/symlink/sn65hvd11.pdf"
742792023,,25%,,,3A,,0.03R,120R,0805,Ferrite Bead,Würth Elektronik,https://www.farnell.com/datasheets/1919974.pdf
810-MPZ1608S601ATA00,,25%,,,1A,,0.15R,600R,0603,Ferrite Bead,Würth Elektronik,https://product.tdk.com/system/files/dam/doc/product/emc/emc/beads/catalog/beads_commercial_power_mpz1608_en.pdf
ACT1210L-201-2P-TL00,200uH,,,,70mA,,5.5R,,3.20mm x 2.50mm,Common Mode Choke,TDK Corporation,https://product.tdk.com/en/system/files/dam/doc/product/emc/emc/cmf_cmc/catalog/cmf_automotive_signal_act1210l-201_en.pdf
BLM18KG221SH1D,,25%,,,2.2A,,0.05R,220R,0603,Ferrite Bead,Murata Electronics,https://www.murata.com/en-us/products/productdata/8796737273886/QNFA9101.pdf
LQM2MPN2R2MG0L,2.2uH,20%,,,1.2A,,0.138R,,0806,Multilayer Inductor,Murata Electronics,https://www.farnell.com/datasheets/3006839.pdf
SMS-R012-1.0,0.012R,1%,5W,,,,,,2512,,Isabellenhütte,https://www.isabellenhuetteusa.com/wp-content/uploads/2024/05/SMS.pdf
TS170R1H272KSBBA0R,2.7nF,10%,,50V,,X7R,,,Radial Leaded,Multilayer Ceramic Capacitor,Suntan,https://www.farnell.com/datasheets/2622414.pdf
```

