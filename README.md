# DMTDB – Electronic Parts Database

A self-hosted parts library built around the **DMT classification schema**.  
Python-only stack: Flask + SQLAlchemy + SQLite.  Single command to run.

---

## Quick Start

```bash
cd dmtdb
pip install -r requirements.txt
python main.py
```

Open **http://localhost:5000**

On first launch the database is created automatically and `DMT_Partslib.csv`
is imported (143 parts, 0 errors).

---

## Project Structure

```
dmtdb/
│
├── main.py                        # Entry point – app factory, seed import, run server
├── config.py                      # Centralised settings (env vars, paths, limits)
├── requirements.txt               # flask >= 3.0, sqlalchemy >= 2.0
│
├── db/                            # ── Database layer ──────────────────────
│   ├── __init__.py                #   Public surface: init_db, get_session, Part, PartField
│   ├── engine.py                  #   Engine bootstrap, SQLite WAL pragmas, session factory
│   └── models.py                  #   ORM: Part (core row) + PartField (EAV for template fields)
│
├── schema/                        # ── DMT classification ──────────────────
│   ├── __init__.py                #   Public surface: load, build_dmtuid, get_fields, …
│   ├── loader.py                  #   Parses dmt_schema.json, builds domain/family lookup maps
│   ├── numbering.py               #   DMTUID build / parse / validate (DMT-TTFFCCSSXXX)
│   └── templates.py               #   Template field resolution per TT+FF family
│
├── import_engine/                 # ── CSV import pipeline ─────────────────
│   ├── __init__.py                #   Public surface: run_import, ImportReport
│   ├── csv_parser.py              #   BOM stripping, encoding detection, header normalisation
│   ├── field_map.py               #   CSV column ↔ Part model attribute mapping constants
│   ├── row_processor.py           #   Single-row validation, UID resolution, Part construction
│   ├── importer.py                #   Orchestrator: csv_parser → row_processor → DB commit
│   └── report.py                  #   ImportReport dataclass with per-row error tracking
│
├── services/                      # ── Business logic ──────────────────────
│   ├── __init__.py                #   Public surface
│   ├── parts_service.py           #   Create / read / update / delete Part records
│   ├── search_service.py          #   Text search + filtered listing with pagination
│   ├── kicad_service.py           #   KiCad-specific lightweight queries
│   └── sequence_service.py        #   XXX auto-allocation (next available per TTFFCCSS group)
│
├── api/                           # ── REST API (/api/v1) ──────────────────
│   ├── __init__.py                #   Blueprint registration
│   ├── errors.py                  #   JSON error handlers (400, 404, 500)
│   ├── routes_parts.py            #   GET/POST/PUT/DELETE /api/v1/parts
│   ├── routes_schema.py           #   GET /api/v1/schema/domains|template|guidelines|cross_cutting
│   ├── routes_kicad.py            #   GET /api/v1/kicad/search|instock
│   └── routes_import.py           #   POST /api/v1/import (JSON response for programmatic use)
│
├── ui/                            # ── Server-rendered HTML ────────────────
│   ├── __init__.py                #   Blueprint registration
│   ├── routes_browse.py           #   GET /              Browse/search table with pagination
│   ├── routes_detail.py           #   GET /part/<uid>    Part detail view
│   ├── routes_forms.py            #   GET|POST /part/add, /part/<uid>/edit, /part/<uid>/delete
│   ├── routes_import.py           #   GET|POST /import   CSV upload page (HTML response)
│   ├── routes_docs.py             #   GET /api/docs      API documentation page
│   ├── datasheet_server.py        #   GET /datasheets/<file>  Secure local file serving
│   └── live_search.py             #   GET /ui-api/search, /ui-api/template_fields  (AJAX JSON)
│
├── static/
│   ├── css/
│   │   └── style.css              #   Dark theme design system
│   └── js/
│       ├── search.js              #   Live search dropdown + barcode scanner support
│       └── add_edit.js            #   Dynamic template fields + CC/SS guideline hints
│
├── templates/                     # ── Jinja2 HTML templates ───────────────
│   ├── base.html                  #   Layout: nav, flash messages, container
│   ├── index.html                 #   Browse page with search, filters, pagination
│   ├── detail.html                #   Part detail: core info, classification, EAV fields
│   ├── add_edit.html              #   Add/edit form with dynamic template field loading
│   ├── import.html                #   CSV upload form + import report display
│   ├── api_docs.html              #   REST API endpoint documentation
│   └── error.html                 #   404 / 500 error page
│
├── datasheets/                    #   Local datasheet PDFs (served by datasheet_server.py)
│
├── dmt_schema.json                #   DMT numbering schema (29 domains, 192 families)
├── dmt_templates.json             #   Field templates per TT+FF (90 templates)
└── DMT_Partslib.csv               #   Seed parts library (143 parts)
```

---

## DMTUID Format

Every part gets a unique identifier following this fixed-width pattern:

```
DMT-TTFFCCSSXXX
     │ │ │ │ └── Per-item sequence 001–999 (auto-assigned)
     │ │ │ └──── Style / vendor bucket 00–99
     │ │ └────── Class / subtype 00–99
     │ └──────── Family 00–99
     └────────── Domain 00–99
```

**Example:** `DMT-02030110001`  
→ Domain 02 (Discrete Semiconductors) → Family 03 (MOSFETs) → Class 01 (N-channel) → Style 10 (DPAK/D2PAK) → Sequence 001

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `DMTDB_HOST` | `0.0.0.0` | Bind address |
| `DMTDB_PORT` | `5000` | Bind port |
| `DMTDB_DB` | `sqlite:///dmtdb.sqlite` | Database URL (supports `postgresql://…`) |
| `DMTDB_SCHEMA` | `./dmt_schema.json` | Path to classification schema |
| `DMTDB_TEMPLATES` | `./dmt_templates.json` | Path to field templates |
| `DMTDB_CSV_SEED` | `./DMT_Partslib.csv` | Seed CSV (imported on first run if DB empty) |
| `DMTDB_DEBUG` | `0` | Set to `1` for Flask debug mode |
| `DMTDB_SECRET` | `dmtdb-dev-key-…` | Flask secret key (change in production) |

---

## REST API

Base URL: `/api/v1`

### Schema

| Method | Endpoint | Description |
|---|---|---|
| GET | `/schema/domains` | List all domains with nested families |
| GET | `/schema/template/{ttff}` | Get ordered field list for a TT+FF key |
| GET | `/schema/guidelines/{ttff}` | Get CC/SS code guideline hints |
| GET | `/schema/cross_cutting` | Cross-cutting class codes (90–99 meanings) |

### Parts CRUD

| Method | Endpoint | Description |
|---|---|---|
| GET | `/parts?q=&tt=&ff=&limit=100&offset=0` | Search / list parts |
| GET | `/parts/{dmtuid}` | Get single part with all fields |
| POST | `/parts` | Create part (JSON: `tt, ff, cc, ss` + fields; XXX auto-assigned) |
| PUT | `/parts/{dmtuid}` | Update fields (JSON body) |
| DELETE | `/parts/{dmtuid}` | Delete a part |

### KiCad Integration

| Method | Endpoint | Description |
|---|---|---|
| GET | `/kicad/search?q=&mpn=&value=&manufacturer=` | Multi-criteria search, KiCad-friendly response |
| GET | `/kicad/instock` | All parts with Quantity > 0 |

Each part can carry optional `kicad_symbol`, `kicad_footprint`, and `kicad_libref` fields.

### CSV Import

| Method | Endpoint | Description |
|---|---|---|
| POST | `/import?replace=0\|1` | Upload CSV (multipart `csv_file` field, or raw body) |

**Response:**
```json
{
  "total_rows": 143,
  "imported": 143,
  "skipped": 0,
  "errors": []
}
```

### cURL Examples

```bash
# Search
curl "http://localhost:5000/api/v1/parts?q=MOSFET&limit=10"

# Get part
curl "http://localhost:5000/api/v1/parts/DMT-02030110001"

# Create
curl -X POST "http://localhost:5000/api/v1/parts" \
  -H "Content-Type: application/json" \
  -d '{"tt":"01","ff":"02","cc":"01","ss":"03","MPN":"RC0603FR-0710KL","Value":"10K"}'

# Update with KiCad fields
curl -X PUT "http://localhost:5000/api/v1/parts/DMT-01020103001" \
  -H "Content-Type: application/json" \
  -d '{"kicad_symbol":"Device:R","kicad_footprint":"Resistor_SMD:R_0603"}'

# Delete
curl -X DELETE "http://localhost:5000/api/v1/parts/DMT-01020103001"

# Import CSV
curl -X POST "http://localhost:5000/api/v1/import" -F "csv_file=@parts.csv"

# KiCad: in-stock parts
curl "http://localhost:5000/api/v1/kicad/instock"

# KiCad: search by MPN
curl "http://localhost:5000/api/v1/kicad/search?mpn=BSS138LT1G"
```

---

## CSV Import Format

The importer accepts CSV files with a header row. Two modes of UID resolution:

1. **Explicit DMTUID column** — if present and valid (`DMT-TTFFCCSSXXX`), used as-is.
2. **TT + FF + CC + SS columns** — if DMTUID is missing/invalid but these four columns exist and are valid, XXX is auto-assigned (next available in the TTFFCCSS group).

Rows that satisfy neither condition are skipped with an error reason.

**Core columns** (stored on the Part row for fast indexing):  
`MPN`, `Value`, `Manufacturer`, `Description`, `Quantity`, `Location`, `Datasheet`

**Template columns** (stored as EAV fields):  
Any additional column that matches the template for the part's TT+FF family.
Columns not in the template are silently ignored (or stored as `extra_json` if no template exists for that family).

**Duplicate handling:**  
By default, duplicate DMTUIDs are rejected. Pass `?replace=1` (API) or check the "Replace existing" box (UI) to overwrite.

---

## UI Features

- **Browse page:** Sortable table with live search, domain filter, pagination (50 per page)
- **Live search dropdown:** Debounced type-ahead (120 ms), keyboard navigation (↑↓ Enter Esc)
- **Barcode scanner:** Enter key checks for exact DMTUID match first, then opens top result
- **Part detail:** Core info, classification badges, template EAV fields, datasheet link
- **Add/edit form:** Dynamic template fields load via AJAX when TT+FF are selected; CC/SS guideline hints displayed
- **CSV import page:** Upload form with replace option, detailed per-row error report
- **API docs page:** Full endpoint reference with cURL examples
- **Dark theme:** Custom design system with CSS variables

---

## Datasheet Handling

The `Datasheet` field accepts two formats:

- **URL** (starts with `http`): Linked directly, opens in new tab.
- **Local filename**: File must be placed in `datasheets/`. Served via `/datasheets/<filename>` with path-traversal protection.

---

## Database

Default: SQLite with WAL mode, foreign keys enabled.  
Migration-ready: set `DMTDB_DB=postgresql://user:pass@host/db` to use PostgreSQL — no code changes needed.

**Tables:**
- `parts` — one row per DMTUID, with indexed columns for MPN, value, manufacturer, location
- `part_fields` — EAV store for template-driven parameters (indexed on `dmtuid + field_name`)

---

## Architecture Notes

**Package responsibilities are strictly separated:**

| Package | Depends on | Purpose |
|---|---|---|
| `config` | nothing | All settings in one place |
| `db` | `config` | Engine, session, ORM models |
| `schema` | nothing (reads JSON files) | Classification, numbering, template resolution |
| `import_engine` | `db`, `schema` | CSV parsing → validation → DB insertion |
| `services` | `db`, `schema` | Business logic (CRUD, search, KiCad, sequencing) |
| `api` | `services`, `db`, `config` | REST endpoints (JSON responses) |
| `ui` | `services`, `db`, `schema`, `config` | HTML pages (Jinja2 rendering) |
| `main` | all of the above | App factory, wiring, startup |

Both `api/routes_import.py` and `ui/routes_import.py` exist — they share a filename but live in different packages. The API version returns JSON for programmatic consumers (curl, scripts, KiCad plugins). The UI version renders the HTML upload page with a form and error report display. Both call `import_engine.run_import()` internally.

---

## License

Internal project — not published.