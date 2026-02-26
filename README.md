# DMTDB – Electronic Parts Database

A self-hosted electronic components inventory system built around the **DMT classification schema**. DMTDB provides a complete solution for organizing, tracking, and integrating your parts library with KiCad EDA software.

**Key Features:**
- Hierarchical part classification using the DMT numbering system (29 domains, 192 families)
- Full KiCad HTTP Library integration for real-time symbol browsing
- Smart value sorting (understands metric prefixes: pico, nano, micro, milli, kilo, mega)
- CSV bulk import with auto-generated UIDs
- REST API for automation and external tool integration
- Dark-themed responsive web interface
- Cross-platform: runs on Windows, Linux, and macOS
- **Label printing** with Code 128 barcodes (4 sizes: 50×30mm, 75×50mm, 100×50mm, 4"×6")
- **Niimbot B1 thermal printer** integration via Bluetooth LE
- **Advanced filtering** with property-based facets and empty value detection
- **RoHS compliance tracking** for each component
- **Date tracking** – sort by when parts were added

**Stack:** Python 3.10+ / Flask 3.0+ / SQLAlchemy 2.0+ / SQLite (or PostgreSQL)

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Web Interface Guide](#web-interface-guide)
3. [Label Printing](#label-printing)
4. [Configuration Reference](#configuration-reference)
5. [DMTUID Format](#dmtuid-format)
6. [REST API](#rest-api)
7. [KiCad HTTP Library Integration](#kicad-http-library-integration)
8. [CSV Import Guide](#csv-import-guide)
9. [Datasheet Handling](#datasheet-handling)
10. [Database](#database)
11. [Project Structure](#project-structure)
12. [Linux Deployment](#linux-deployment)
13. [Architecture Notes](#architecture-notes)

---

## Quick Start

### Windows

```powershell
cd SW_PartsDB
pip install -r requirements.txt
python main.py
```

### Linux / macOS

```bash
cd SW_PartsDB
chmod +x start.sh
./start.sh
```

The `start.sh` script automatically:
- Creates a Python virtual environment (if not present)
- Installs all dependencies
- Starts the server

**Access the web interface:** Open **http://localhost:5000** in your browser.

On first launch:
1. The SQLite database is created automatically
2. The DMT schema is loaded (29 domains, 192 families, 90 field templates)
3. The seed CSV (`DMT_Partslib.csv`) is imported if the database is empty

---

## Web Interface Guide

### Main Browse Page

The browse page is your primary interface for finding and managing parts.

![Browse Page Screenshot](static/img/browse_page.png)

**Features:**

| Feature | Description |
|---------|-------------|
| **Live Search** | Type in the search box and results appear instantly (120ms debounce). Searches across DMTUID, MPN, Value, Manufacturer, and Description fields. |
| **Domain Filter** | Dropdown to filter by component domain (Passives, Semiconductors, etc.). |
| **Sortable Columns** | Click any column header to sort. Click again to reverse. Works with smart value sorting for component values. Includes **Added** column to see newest parts. |
| **KiCad Icons** | Three icons show which KiCad files are linked to each part: Symbol (op-amp icon), Footprint (IC package icon), 3D Model (cube icon). |
| **Pagination** | 50 parts per page with Previous/Next navigation. |
| **Barcode Scanner Support** | Press Enter after typing a DMTUID to jump directly to that part. |

**Smart Value Sorting:**
The "Value" column understands metric prefixes, so components sort in the correct order:
- `100pF` → `1nF` → `10nF` → `100nF` → `1uF` → `10uF`
- `1R` → `10R` → `100R` → `1K` → `10K` → `100K` → `1M`
- Values like `4K7` (4.7K) and `3.3R 1%` (3.3 ohms) are correctly parsed.

---

### Part Detail Page

Click any part row to view its complete details.

![Part Detail Screenshot](static/img/part_detail.png)

**Sections:**

| Section | Contents |
|---------|----------|
| **Header** | DMTUID, MPN, value badge, quantity badge |
| **Core Info** | Manufacturer, description, RoHS status (Yes/No), location, datasheet link |
| **Classification** | Domain, Family, Class, Style badges with human-readable names |
| **Template Fields** | All EAV fields specific to this component type (e.g., Capacitance, Voltage - Rated, Tolerance for capacitors) |
| **KiCad Links** | Symbol, footprint, and 3D model references |
| **Actions** | Edit and Delete buttons |

---

### Add/Edit Part Form

Create new parts or modify existing ones.

![Add Edit Screenshot](static/img/add_edit_form.png)

**How It Works:**

1. **Select Domain (TT)** – Choose from 29 component domains
2. **Select Family (FF)** – Families filter based on selected domain
3. **Template Fields Load** – Once TT+FF are selected, the form dynamically loads all relevant fields for that component type
4. **CC/SS Guidelines** – Hints appear showing recommended codes for Class and Style
5. **Enter Data** – Fill in MPN, Value, and all template-specific fields
6. **Save** – The XXX sequence is auto-assigned (next available in the TTFFCCSS group)

**KiCad File Upload:**

The edit form includes a drag-and-drop zone for uploading KiCad library files:

| File Type | What Happens |
|-----------|--------------|
| `.kicad_sym` | Opens a modal to edit symbol properties (Value, Footprint, Datasheet, etc.). Properties are pre-filled from part data. Saved to `kicad_libs/symbols/`. |
| `.kicad_mod` | Saved directly to `kicad_libs/footprints/`. 3D model paths are auto-converted to `${DMTDB_3D}/filename.step`. |
| `.step` / `.wrl` | Saved to `kicad_libs/3dmodels/`. |

Files are first staged in a temporary area (2-hour auto-cleanup) until the form is submitted.

---

### CSV Import Page

Bulk import parts from CSV files.

![Import Screenshot](static/img/import_page.png)

**Options:**
- **Replace Existing** – Check this to overwrite parts with duplicate DMTUIDs (default: skip duplicates)

**After Import:**
A detailed report shows:
- Total rows processed
- Successfully imported count
- Skipped count with per-row error reasons

---

### KiCad Libraries Page

Manage your KiCad symbol, footprint, and 3D model files.

![Libraries Screenshot](static/img/libs_page.png)

Access at `/libs` to see all files in your `kicad_libs/` folder organized by type.

---

## Label Printing

DMTDB includes a dedicated label printing system for component identification on ESD bags, reels, and bins.

### Label Sizes

| Size | Dimensions | Use Case |
|------|------------|----------|
| **50×30mm** | Small | Individual SMD components, ESD bags |
| **75×50mm** | Medium | Reels, component boxes |
| **100×50mm** | Large | Larger packaging, bins |
| **4"×6"** | Shipping | Full-size shipping labels |

### Label Contents

Each label includes:
- **DMTUID** – The unique component identifier
- **MPN** – Manufacturer Part Number
- **MFR** – Manufacturer name
- **Value** – Component value (e.g., 10K, 100nF)
- **Package** – Package type (e.g., 0603, SOT-23)
- **Description** – Brief component description
- **Code 128 Barcode** – Machine-scannable DMTUID

### Using the Labels Page

Access at `/labels` to:

1. **Search & Select** – Find parts using the search bar and domain/family filters
2. **Select Parts** – Check individual parts or use "Select All" for the current page
3. **Choose Size** – Select from the 4 available label sizes
4. **Preview** – Click a part to see a live label preview
5. **Print** – Print via browser, download as SVG, or print directly to a Niimbot printer

### Advanced Filtering

The labels page includes powerful filtering options:

- **Domain (TT)** – Filter by component category
- **Family (FF)** – Filter by specific family within a domain
- **Class (CC)** and **Style (SS)** – Fine-grained classification filters
- **Property Facets** – Dynamic filters based on component properties (e.g., Package, Voltage, Tolerance)
- **Location Filter** – Filter by storage location, includes "(Empty)" option to find unlocated parts
- **Sort by Added** – Click the "Added" column to see most recently added parts first

### Niimbot B1 Printer Integration

DMTDB supports direct printing to Niimbot B1 thermal label printers via Bluetooth LE.

**Requirements:**
- Niimbot B1 thermal printer (or compatible models: B18, B21)
- Computer with Bluetooth LE support
- Python `bleak` package (included in requirements.txt)

**Setup:**

1. Turn on your Niimbot printer
2. Click the **Niimbot** button in the top navigation bar
3. Click **Scan** to discover nearby printers
4. Select your printer from the dropdown
5. Click **Connect**

The connection indicator turns green when connected. The connection persists across page navigation.

![Niimbot Connection](static/img/niimbot.png)

**Printing:**

| Action | How |
|--------|-----|
| **Single Label** | Click a part to preview, then "Print to Niimbot" |
| **Batch Print** | Select multiple parts, click "Niimbot (N)" button |

**Print Settings:**
- **Density** – Adjustable 1-5 (1=light, 5=dark). Default: 3

### Label API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/labels` | Labels page with search, selection, and printing |
| GET | `/labels/svg/{dmtuid}?size=50x30` | Generate SVG label for a part |
| GET | `/labels/niimbot/scan` | Scan for Niimbot printers |
| POST | `/labels/niimbot/connect` | Connect to a Niimbot printer |
| POST | `/labels/niimbot/disconnect` | Disconnect from printer |
| GET | `/labels/niimbot/status` | Check connection status |
| POST | `/labels/niimbot/print` | Print a single label |
| POST | `/labels/niimbot/batch` | Print multiple labels |

**cURL Examples:**

```bash
# Generate SVG label
curl "http://localhost:5000/labels/svg/DMT-01020103001?size=75x50"

# Scan for Niimbot printers
curl "http://localhost:5000/labels/niimbot/scan?timeout=10"

# Connect to a printer
curl -X POST "http://localhost:5000/labels/niimbot/connect" \
  -H "Content-Type: application/json" \
  -d '{"address": "AA:BB:CC:DD:EE:FF", "model": "b1"}'

# Print a label
curl -X POST "http://localhost:5000/labels/niimbot/print" \
  -H "Content-Type: application/json" \
  -d '{"dmtuid": "DMT-01020103001", "size": "50x30", "density": 3}'

# Batch print
curl -X POST "http://localhost:5000/labels/niimbot/batch" \
  -H "Content-Type: application/json" \
  -d '{"dmtuids": ["DMT-01020103001", "DMT-01020103002"], "size": "50x30", "density": 3}'
```

---

## Configuration Reference

All settings can be configured via environment variables. Default values work out of the box for local development.

### Core Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `DMTDB_HOST` | `0.0.0.0` | Network interface to bind. Use `127.0.0.1` to only allow local connections. |
| `DMTDB_PORT` | `5000` | HTTP port for the web server. |
| `DMTDB_DEBUG` | `0` | Set to `1` to enable Flask debug mode with auto-reload. |
| `DMTDB_SECRET` | `dmtdb-dev-key-...` | Flask secret key for session encryption. **Change this in production!** |

### Database Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `DMTDB_DB` | `sqlite:///dmtdb.sqlite` | SQLAlchemy database URL. Supports SQLite and PostgreSQL. |

**Examples:**
```bash
# SQLite (default, stored in project folder)
DMTDB_DB=sqlite:///dmtdb.sqlite

# SQLite (absolute path)
DMTDB_DB=sqlite:////home/user/data/dmtdb.sqlite

# PostgreSQL
DMTDB_DB=postgresql://user:password@localhost/dmtdb
```

### Schema and Data Files

| Variable | Default | Description |
|----------|---------|-------------|
| `DMTDB_SCHEMA` | `./dmt_schema.json` | Path to the DMT classification schema defining domains, families, and guidelines. |
| `DMTDB_TEMPLATES` | `./dmt_templates.json` | Path to field templates defining which fields each component family uses. |
| `DMTDB_CSV_SEED` | `./DMT_Partslib.csv` | CSV file to import on first run if database is empty. Set to empty string to disable. |

### KiCad Integration Paths

| Variable | Default | Description |
|----------|---------|-------------|
| `DMTDB_KICAD_SYMBOLS_DIR` | `./kicad_libs/symbols` | Directory for KiCad symbol files (`.kicad_sym`). |
| `DMTDB_KICAD_FOOTPRINTS_DIR` | `./kicad_libs/footprints` | Directory for KiCad footprint files (`.kicad_mod`). |
| `DMTDB_KICAD_3DMODELS_DIR` | `./kicad_libs/3dmodels` | Directory for 3D model files (`.step`, `.wrl`). |
| `DMTDB_KICAD_HTTPLIB_FILE` | `./kicad_libs/DMTDB.kicad_httplib` | HTTP library configuration file for KiCad. |

### Multi-PC Client Sync

![Multi-PC Client Sync](static/img/client.png)

For local network deployments where multiple workstations share the server:

1. **Navigate to Client Setup** (`/client-setup`) on each PC
2. **Configure local paths** where KiCad libraries should be extracted
3. **Download libraries** using the green "Download Libs" button
4. **Extract ZIP** to the configured local paths
5. **Mark as Synced** to record the sync time

The server tracks each client by IP address and notifies when updates are available. The Client Setup page shows:
- Current sync status (up-to-date or needs sync)
- All registered clients and their sync states
- Library version hash for change detection

![Multi-PC Client Sync](static/img/client2.png)

### Display Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `DMTDB_PAGE_SIZE` | `50` | Number of parts per page on the browse view. |
| `DMTDB_SEARCH_DROPDOWN_LIMIT` | `12` | Maximum results in the live search dropdown. |

### Example: Production Configuration

```bash
# Run on port 8080, bind only to localhost (behind reverse proxy)
export DMTDB_HOST=127.0.0.1
export DMTDB_PORT=8080
export DMTDB_DEBUG=0
export DMTDB_SECRET="your-long-random-secret-key-here"
export DMTDB_DB="postgresql://dmtdb:secretpass@localhost/dmtdb"
```

---

## DMTUID Format

Every part receives a unique identifier following this fixed-width pattern:

```
DMT-TTFFCCSSXXX
    ││ ││ ││ │└── Per-item sequence 001–999 (auto-assigned)
    ││ ││ │└──── Style / vendor bucket 00–99
    ││ │└────── Class / subtype 00–99
    │└──────── Family 00–99
    └────────── Domain 00–99
```

### Segment Meanings

| Segment | Digits | Description | Example |
|---------|--------|-------------|---------|
| **TT** | 2 | Domain – broad component category | `01` = Passive Components |
| **FF** | 2 | Family – specific component type within the domain | `02` = Resistors |
| **CC** | 2 | Class – subtype, technology, or rating category | `01` = Chip resistors |
| **SS** | 2 | Style – package, vendor tier, or other bucket | `03` = 0603 package |
| **XXX** | 3 | Sequence – auto-assigned unique number within the group | `001` |

### Example Breakdown

```
DMT-01020103001
    │ │ │ │ └── 001 = First part in this group
    │ │ │ └──── 03 = 0603 package style
    │ │ └────── 01 = Chip resistors class
    │ └──────── 02 = Resistors family
    └────────── 01 = Passive Components domain
```

This resolves to: **"Passive Components → Resistors → Chip resistors → 0603 package → Part #001"**

### Domain Overview

The DMT schema includes 29 domains:

| TT | Domain |
|----|--------|
| 01 | Passive Components (Capacitors, Resistors, Inductors, Crystals...) |
| 02 | Discrete Semiconductors (Diodes, Transistors, MOSFETs, IGBTs...) |
| 03 | Integrated Circuits (Op-amps, Logic, MCUs, Memory...) |
| 04 | Power Management (Regulators, Converters, Supervisors...) |
| 05 | Connectors (Headers, USB, RF, Card slots...) |
| 06 | Electromechanical (Relays, Switches, Buttons...) |
| ... | (See `dmt_schema.json` for complete list) |

### Cross-Cutting Class Codes (90-99)

Class codes 90-99 have special meanings across all domains:

| CC | Meaning |
|----|---------|
| 90 | Evaluation/Development Kit |
| 91 | Reference Design |
| 92 | Discontinued/Legacy |
| 93 | Engineering Sample |
| 94-99 | Reserved for future use |

---

## REST API

Base URL: `/api/v1`

All API endpoints return JSON. Errors return `{"error": "message"}` with appropriate HTTP status codes.

### Schema Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/schema/domains` | List all domains with nested families |
| GET | `/schema/template/{ttff}` | Get ordered field list for a TT+FF key |
| GET | `/schema/guidelines/{ttff}` | Get CC/SS code guidelines and hints |
| GET | `/schema/cross_cutting` | List cross-cutting class code meanings |

### Parts CRUD Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/parts` | Search and list parts with filters and pagination |
| GET | `/parts/{dmtuid}` | Get a single part with all fields |
| POST | `/parts` | Create a new part (XXX auto-assigned) |
| PUT | `/parts/{dmtuid}` | Update an existing part |
| DELETE | `/parts/{dmtuid}` | Delete a part |

**GET /parts Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `q` | string | Free text search (MPN, Value, Description) |
| `tt` | string | Filter by domain code |
| `ff` | string | Filter by family code |
| `cc` | string | Filter by class code |
| `ss` | string | Filter by style code |
| `props` | string | Property filters (JSON or URL-encoded, e.g., `{"Location":["Bin A"]}`) |
| `sort` | string | Column to sort by: `dmtuid`, `mpn`, `value`, `quantity`, `location`, `manufacturer`, `created_at` |
| `order` | string | `asc` or `desc` |
| `limit` | int | Results per page (default: 100) |
| `offset` | int | Pagination offset (default: 0) |

### KiCad Integration Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/kicad/search` | Multi-criteria search returning KiCad-friendly data |
| GET | `/kicad/instock` | All parts with Quantity > 0 |

**GET /kicad/search Query Parameters:**

| Parameter | Description |
|-----------|-------------|
| `q` | General search across all fields |
| `mpn` | Exact MPN match |
| `value` | Exact value match |
| `manufacturer` | Exact manufacturer match |

### KiCad HTTP Library Endpoint

DMTDB implements the KiCad HTTP Library protocol for real-time symbol browsing:

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/kicad/v1/categories.json` | List categories (domains + families) |
| GET | `/kicad/v1/parts.json` | List parts, optionally filtered by category |
| GET | `/kicad/v1/parts/{id}.json` | Get full part details including symbol fields |

### Library Management Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/libs` | List all KiCad library files |
| POST | `/libs/stage/session` | Create a staging session for uploads |
| POST | `/libs/stage` | Stage a file for later processing |
| GET | `/libs/stage/{session_id}` | Get staged file info |
| DELETE | `/libs/stage/{session_id}` | Clear staged files |
| POST | `/libs/upload` | Direct upload (bypasses staging) |
| GET | `/libs/download` | Download all libraries as ZIP |

### Client Sync Endpoints

For multi-PC setups, DMTDB tracks each client by IP and provides sync status:

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/libs/client` | Get/create config for current client (by IP) |
| POST | `/libs/client` | Save client's local library paths |
| POST | `/libs/client/mark-synced` | Mark client as synced with current libs |
| GET | `/libs/sync/status` | Check if client needs to sync |
| GET | `/libs/clients` | List all registered clients (admin view) |

**Client Setup UI:** Navigate to `/client-setup` to configure local paths and track sync status.

### CSV Import Endpoint

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/import?replace=0\|1` | Import CSV file |

**Import accepts:**
- Multipart form upload with field name `csv_file`
- Raw CSV body with `Content-Type: text/csv`

### cURL Examples

```bash
# Search parts by keyword
curl "http://localhost:5000/api/v1/parts?q=MOSFET&limit=10"

# Get a specific part by DMTUID
curl "http://localhost:5000/api/v1/parts/DMT-01020103001"

# Create a new part (XXX will be auto-assigned)
curl -X POST "http://localhost:5000/api/v1/parts" \
  -H "Content-Type: application/json" \
  -d '{
    "tt": "01",
    "ff": "02", 
    "cc": "01",
    "ss": "03",
    "MPN": "RC0603FR-0710KL",
    "Manufacturer": "Yageo",
    "Value": "10K",
    "Resistance": "10kΩ",
    "Tolerance": "1%",
    "Power (Watts)": "0.1W",
    "Package / Case": "0603"
  }'

# Update KiCad fields on an existing part
curl -X PUT "http://localhost:5000/api/v1/parts/DMT-01020103001" \
  -H "Content-Type: application/json" \
  -d '{
    "kicad_symbol": "DMTDB_PassiveComponents_Resistors:R_10K_0603",
    "kicad_footprint": "R_0603_1608Metric"
  }'

# Delete a part
curl -X DELETE "http://localhost:5000/api/v1/parts/DMT-01020103001"

# Import a CSV file
curl -X POST "http://localhost:5000/api/v1/import?replace=0" \
  -F "csv_file=@my_parts.csv"

# Import with replace mode (overwrite duplicates)
curl -X POST "http://localhost:5000/api/v1/import?replace=1" \
  -F "csv_file=@my_parts.csv"

# KiCad: Get all in-stock parts
curl "http://localhost:5000/api/v1/kicad/instock"

# KiCad: Search by exact MPN
curl "http://localhost:5000/api/v1/kicad/search?mpn=BSS138LT1G"

# List available KiCad libraries
curl "http://localhost:5000/api/v1/libs"
```

---

## KiCad HTTP Library Integration

DMTDB integrates with KiCad in two ways:
1. **HTTP Library** (symbols only) – Browse and place symbols directly from KiCad's symbol chooser
2. **Downloaded Libraries** (footprints, 3D models) – Download library files to your local machine for offline use

### Understanding the Split

KiCad's HTTP Library feature only supports symbols. Footprints and 3D models must be stored locally. DMTDB provides a **Download Libs** button in the navigation bar that packages all library files into a ZIP for easy setup.

### Quick Start

1. Click **Download Libs** in the DMTDB navigation bar
2. Extract the ZIP to a permanent location (e.g., `C:\KiCad_Libs\DMTDB\` or `~/kicad_libs/dmtdb/`)
3. Configure KiCad paths to point to the extracted folders
4. Add the HTTP library for symbol browsing

### File Organization

**On the server:**
```
kicad_libs/
├── DMTDB.kicad_httplib        # HTTP library configuration
├── symbols/                    # .kicad_sym files (served via HTTP)
├── footprints/                 # .kicad_mod files (download for local use)
└── 3dmodels/                   # .step files (download for local use)
```

**On your workstation (after download):**
```
C:\KiCad_Libs\DMTDB\           # Or any location you choose
├── symbols/                    # Downloaded symbol files
├── footprints/                 # Downloaded footprint files
├── 3dmodels/                   # Downloaded 3D model files
└── README.md                   # Setup instructions
```

### KiCad Configuration

#### Step 1: Download and Extract Libraries

1. In DMTDB, click the green **Download Libs** button in the navigation bar
2. Save `DMTDB_KiCad_Libraries.zip` to your computer
3. Extract to a permanent location:
   - **Windows:** `C:\KiCad_Libs\DMTDB\`
   - **Linux:** `~/kicad_libs/dmtdb/`
   - **macOS:** `~/Documents/KiCad_Libs/DMTDB/`

#### Step 2: Configure Path Variables

In KiCad, go to **Preferences → Configure Paths** and add:

| Name | Windows Path | Linux/macOS Path |
|------|--------------|------------------|
| `DMTDB_ROOT` | `C:/KiCad_Libs/DMTDB/` | `~/kicad_libs/dmtdb/` |
| `DMTDB_SYM` | `${DMTDB_ROOT}/symbols/` | `${DMTDB_ROOT}/symbols/` |
| `DMTDB_FOOTPRINT` | `${DMTDB_ROOT}/footprints/` | `${DMTDB_ROOT}/footprints/` |
| `DMTDB_3D` | `${DMTDB_ROOT}/3dmodels/` | `${DMTDB_ROOT}/3dmodels/` |

> **Note:** Use forward slashes `/` even on Windows. KiCad handles path conversion.

#### Step 3: Add Footprint Library

In KiCad, go to **Preferences → Manage Footprint Libraries → Global Libraries**:

1. Click **Add library** (+)
2. Set:
   - **Nickname:** `DMTDB`
   - **Library Path:** `${DMTDB_FOOTPRINT}`
   - **Library Type:** KiCad

#### Step 4: Add Symbol Drawing Libraries

The HTTP library provides part metadata, but the actual symbol **drawings** come from `.kicad_sym` files. Add each symbol library to **Preferences → Manage Symbol Libraries → Global Libraries**:

| Nickname (must match exactly) | Library Path |
|-------------------------------|-------------|
| `DMTDB_PassiveComponents_Capacitors` | `${DMTDB_SYM}/DMTDB_PassiveComponents_Capacitors.kicad_sym` |
| `DMTDB_PassiveComponents_Resistors` | `${DMTDB_SYM}/DMTDB_PassiveComponents_Resistors.kicad_sym` |
| `DMTDB_PassiveComponents_Inductors` | `${DMTDB_SYM}/DMTDB_PassiveComponents_Inductors.kicad_sym` |

> **Critical:** The nicknames **must match exactly** as shown. Parts in the database reference symbols like `DMTDB_PassiveComponents_Resistors:R_Chip`. A mismatched nickname causes "symbol not found" errors.

#### Step 5: Add HTTP Symbol Library

In KiCad, go to **Preferences → Manage Symbol Libraries → Global Libraries**:

1. Click **Add library** (+)
2. Set:
   - **Nickname:** `DMTDB` *(must be exactly this name)*
   - **Library Path:** `${DMTDB_ROOT}/kicad_libs/DMTDB.kicad_httplib`
   - **Library Type:** KiCad (HTTP)

> **Critical:** The nickname **must be exactly `DMTDB`**. Parts in the database reference symbols using this library name (e.g., `DMTDB:R_Chip`). Using a different nickname will cause symbol lookup failures.

> **Important:** The `.kicad_httplib` file must be a **local file path**, not an HTTP URL. KiCad reads this local file, which contains the `root_url` pointing to the DMTDB server API. Edit the file to set the correct server address (e.g., `http://localhost:5000/kicad/v1/` or `http://192.168.1.100:5000/kicad/v1/`).

#### Step 6: Browse Parts

1. Open the schematic editor
2. Press **A** to add a symbol
3. Expand **DMTDB** in the symbol browser
4. Browse by category (e.g., "01 Passive Components → 02 Resistors")
5. Place the symbol – properties are auto-filled from the database

### Keeping Libraries in Sync

When you add new footprints or 3D models to DMTDB, update your local copy:

1. Click **Download Libs** in DMTDB
2. Extract the ZIP, overwriting existing files
3. KiCad will automatically use the updated files

**Tip:** Consider using a sync script or scheduled task for team environments.

### Symbol Properties

When placing a symbol from DMTDB, these properties are auto-filled:

| Property | Source |
|----------|--------|
| `Reference` | Standard (R, C, U, etc.) |
| `Value` | Part's Value field (or generated from parameters) |
| `Footprint` | `DMTDB:{footprint_name}` format |
| `Datasheet` | Part's Datasheet URL |
| `Description` | Part's Description field |
| `MFR` | Manufacturer name |
| `MPN` | Manufacturer Part Number |
| `DMTUID` | Database unique ID for BOM generation |
| `ROHS` | RoHS compliance status |

### Uploading KiCad Files

When editing a part in DMTDB, drag and drop KiCad files onto the upload zone:

| File Type | Processing |
|-----------|------------|
| **Symbol** (`.kicad_sym`) | Opens property editor. Saved to `symbols/` with naming like `DMTDB_PassiveComponents_Resistors.kicad_sym`. |
| **Footprint** (`.kicad_mod`) | Saved to `footprints/`. 3D model paths auto-converted to `${DMTDB_3D}/...`. |
| **3D Model** (`.step`, `.wrl`) | Saved to `3dmodels/`. |

### Symbol Naming Convention

Symbol libraries are organized by domain and family:
```
DMTDB_{DomainName}_{FamilyName}.kicad_sym
```

Examples:
- `DMTDB_PassiveComponents_Capacitors.kicad_sym`
- `DMTDB_PassiveComponents_Resistors.kicad_sym`
- `DMTDB_DiscreteSemiconductors_MOSFETs.kicad_sym`

### Network vs Local Setup

| Aspect | Local Setup | Network Setup |
|--------|-------------|---------------|
| **Server Location** | Same machine as KiCad | Separate server |
| **HTTP Library URL** | `http://localhost:5000/...` | `http://192.168.1.x:5000/...` |
| **Footprints/3D** | Downloaded to local path | Downloaded to local path (each workstation) |
| **Sync Required** | No (same machine) | Yes (download updates periodically) |

---

## CSV Import Guide

### Supported Formats

- UTF-8 or UTF-8 with BOM encoding
- Standard CSV with comma separation
- Header row required

### UID Resolution

The importer determines the DMTUID in two ways:

1. **Explicit DMTUID column** – If a valid `DMT-TTFFCCSSXXX` value is present, it's used as-is
2. **Category columns** – If `TT`, `FF`, `CC`, `SS` columns are present and valid, XXX is auto-assigned

Rows missing both are skipped with an error.

### Core Fields

These columns are stored directly on the Part table for fast searching:

| Column Name | Description |
|-------------|-------------|
| `MPN` | Manufacturer Part Number |
| `Manufacturer` | Manufacturer name |
| `Value` | Component value (e.g., "10K", "100nF") |
| `Description` | Human-readable description |
| `Quantity` | Inventory count |
| `Location` | Storage location |
| `Datasheet` | URL or local filename |
| `Distributor` | Where to purchase |
| `KiCadSymbol` | KiCad symbol reference |
| `KiCadFootprint` | KiCad footprint reference |
| `KiCadLibRef` | KiCad library reference |

### Template Fields

Any additional columns that match the template for the part's TT+FF family are stored as EAV (Entity-Attribute-Value) records. For example, for capacitors (TT=01, FF=01):

- Capacitance
- Tolerance
- Voltage - Rated
- Dielectric
- Package / Case
- etc.

Unrecognized columns are silently ignored (or stored in `extra_json` if no template exists).

### Duplicate Handling

| Mode | Behavior |
|------|----------|
| **Default** (`replace=0`) | Duplicate DMTUIDs are rejected with an error |
| **Replace** (`replace=1`) | Existing parts with matching DMTUIDs are overwritten |

### Example CSV

```csv
DMTUID,MPN,Manufacturer,Value,Quantity,Location,Capacitance,Voltage - Rated,Package / Case
,GRM188R71H104KA93D,Murata,100nF,50,A1-01,100nF,50V,0603
,GRM155R71C104KA88D,Murata,100nF,25,A1-02,100nF,16V,0402
DMT-01010101001,CL21B104KBCNNNC,Samsung,100nF,100,A1-03,100nF,50V,0805
```

Row 2 and 3 will get auto-assigned DMTUIDs. Row 4 uses the explicit DMTUID.

---

## Datasheet Handling

The `Datasheet` field accepts two formats:

| Format | Behavior |
|--------|----------|
| **URL** (starts with `http://` or `https://`) | Displayed as a clickable link, opens in new tab |
| **Local filename** | Served from `datasheets/` folder via `/datasheets/{filename}` |

### Local Datasheet Setup

1. Create a `datasheets/` folder in the project root
2. Place PDF files there
3. Set the part's Datasheet field to just the filename (e.g., `BSS138.pdf`)
4. Click the datasheet link to view – served with path-traversal protection

---

## Database

### Default Configuration

DMTDB uses SQLite by default with these optimizations:
- **WAL mode** (Write-Ahead Logging) for better concurrent read performance
- **Foreign keys enabled** for data integrity
- Database file: `dmtdb.sqlite` in the project root

### PostgreSQL Support

For production or multi-user deployments, PostgreSQL is recommended:

```bash
export DMTDB_DB="postgresql://username:password@host/database"
```

No code changes required – SQLAlchemy handles the differences.

### Schema

**`parts` table:**
| Column | Type | Description |
|--------|------|-------------|
| `dmtuid` | VARCHAR(18) PK | Unique identifier |
| `tt`, `ff`, `cc`, `ss`, `xxx` | VARCHAR | Classification segments |
| `mpn` | VARCHAR | Manufacturer Part Number (indexed) |
| `manufacturer` | VARCHAR | Manufacturer name (indexed) |
| `value` | VARCHAR | Component value (indexed) |
| `description` | TEXT | Human-readable description |
| `quantity` | VARCHAR | Inventory count |
| `location` | VARCHAR | Storage location (indexed) |
| `datasheet` | VARCHAR | URL or filename |
| `distributor` | VARCHAR | Purchase source |
| `kicad_symbol` | VARCHAR | KiCad symbol reference |
| `kicad_footprint` | VARCHAR | KiCad footprint reference |
| `kicad_libref` | VARCHAR | KiCad library reference |
| `extra_json` | TEXT | JSON blob for non-template fields |

**`part_fields` table (EAV):**
| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Auto-increment ID |
| `dmtuid` | VARCHAR FK | Reference to parts table |
| `field_name` | VARCHAR | Field name (indexed) |
| `field_value` | TEXT | Field value |

---

## Project Structure

```
SW_PartsDB/
│
├── main.py                     # Entry point – app factory, seed import, run server
├── config.py                   # Centralized settings (env vars, paths, limits)
├── requirements.txt            # Dependencies: flask >= 3.0, sqlalchemy >= 2.0, kiutils >= 1.4
├── start.sh                    # Linux/macOS startup script
├── install-service.sh          # Linux systemd service installer
├── uninstall-service.sh        # Linux systemd service remover
│
├── db/                         # ── Database Layer ─────────────────────────
│   ├── __init__.py             #   Public surface: init_db, get_session, Part, PartField
│   ├── engine.py               #   Engine bootstrap, SQLite WAL pragmas, session factory
│   └── models.py               #   ORM: Part + PartField models
│
├── schema/                     # ── DMT Classification ─────────────────────
│   ├── __init__.py             #   Public surface: load, build_dmtuid, get_fields, etc.
│   ├── loader.py               #   Parses dmt_schema.json, builds lookup maps
│   ├── numbering.py            #   DMTUID build / parse / validate
│   └── templates.py            #   Template field resolution per TT+FF family
│
├── import_engine/              # ── CSV Import Pipeline ────────────────────
│   ├── __init__.py             #   Public surface: run_import, ImportReport
│   ├── csv_parser.py           #   BOM handling, encoding detection, header cleanup
│   ├── field_map.py            #   CSV column ↔ Part attribute mapping
│   ├── row_processor.py        #   Single-row validation, UID resolution
│   ├── importer.py             #   Orchestrator: parser → processor → DB commit
│   └── report.py               #   ImportReport dataclass
│
├── services/                   # ── Business Logic ─────────────────────────
│   ├── __init__.py             #   Public surface
│   ├── parts_service.py        #   CRUD operations for Part records
│   ├── search_service.py       #   Text search + filtered listing + smart value sorting
│   ├── kicad_service.py        #   KiCad-specific queries
│   ├── kicad_staging.py        #   In-memory staging for KiCad file uploads
│   ├── kicad_symbol_processor.py  #   Symbol property extraction and modification
│   └── sequence_service.py     #   XXX auto-allocation
│
├── api/                        # ── REST API (/api/v1) ─────────────────────
│   ├── __init__.py             #   Blueprint registration
│   ├── errors.py               #   JSON error handlers
│   ├── routes_parts.py         #   GET/POST/PUT/DELETE /parts
│   ├── routes_schema.py        #   GET /schema/* endpoints
│   ├── routes_kicad.py         #   GET /kicad/* endpoints + HTTP Library protocol
│   ├── routes_libs.py          #   GET/POST /libs/* for library management
│   └── routes_import.py        #   POST /import (JSON response)
│
├── ui/                         # ── Server-Rendered HTML ───────────────────
│   ├── __init__.py             #   Blueprint registration
│   ├── routes_browse.py        #   GET / (browse page with sorting)
│   ├── routes_detail.py        #   GET /part/{uid} (detail view)
│   ├── routes_forms.py         #   GET/POST /part/add, /part/{uid}/edit, delete
│   ├── routes_import.py        #   GET/POST /import (HTML upload page)
│   ├── routes_docs.py          #   GET /api/docs
│   ├── datasheet_server.py     #   GET /datasheets/{file}
│   └── live_search.py          #   GET /ui-api/* (AJAX endpoints)
│
├── static/
│   ├── css/style.css           #   Dark theme design system
│   ├── js/search.js            #   Live search + barcode support
│   ├── js/add_edit.js          #   Dynamic form fields
│   ├── js/adv_search.js        #   Advanced search UI
│   └── img/                    #   Screenshots (placeholder)
│
├── templates/                  # ── Jinja2 Templates ───────────────────────
│   ├── base.html               #   Layout with nav, flash messages
│   ├── index.html              #   Browse page with sortable columns
│   ├── detail.html             #   Part detail view
│   ├── add_edit.html           #   Add/edit form with KiCad upload zone
│   ├── import.html             #   CSV import page
│   ├── libs.html               #   KiCad libraries page
│   ├── api_docs.html           #   API documentation
│   └── error.html              #   Error page
│
├── kicad_libs/                 # ── KiCad Library Files ────────────────────
│   ├── DMTDB.kicad_httplib     #   HTTP library configuration
│   ├── README.md               #   KiCad setup instructions
│   ├── symbols/                #   .kicad_sym files
│   ├── footprints/             #   .kicad_mod files
│   └── 3dmodels/               #   .step and .wrl files
│
├── datasheets/                 #   Local datasheet PDFs (create if needed)
│
├── dmt_schema.json             #   DMT classification (29 domains, 192 families)
├── dmt_templates.json          #   Field templates (90+ templates)
└── DMT_Partslib.csv            #   Seed parts library
```

---

## Linux Deployment

### Manual Startup

```bash
cd /path/to/SW_PartsDB
./start.sh
```

### Automatic Startup (systemd Service)

Install DMTDB as a systemd service that starts automatically on boot:

```bash
# Install the service
sudo ./install-service.sh

# Check status
sudo systemctl status dmtdb

# View logs
sudo journalctl -u dmtdb -f

# Stop/restart
sudo systemctl stop dmtdb
sudo systemctl restart dmtdb
```

To remove the service:

```bash
sudo ./uninstall-service.sh
```

### Production Recommendations

1. **Run behind a reverse proxy** (nginx, Caddy) for SSL termination
2. **Use PostgreSQL** instead of SQLite for better concurrent performance
3. **Set `DMTDB_DEBUG=0`** in production
4. **Change `DMTDB_SECRET`** to a strong random value
5. **Bind to `127.0.0.1`** when behind a reverse proxy

**Example nginx configuration:**

```nginx
server {
    listen 443 ssl http2;
    server_name parts.example.com;
    
    ssl_certificate /etc/ssl/certs/parts.crt;
    ssl_certificate_key /etc/ssl/private/parts.key;
    
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## Architecture Notes

### Package Dependencies

The codebase follows strict layering to maintain separation of concerns:

| Package | Depends On | Purpose |
|---------|------------|---------|
| `config` | nothing | All settings centralized |
| `db` | `config` | Engine, session, ORM models |
| `schema` | nothing (reads JSON) | Classification, numbering, templates |
| `import_engine` | `db`, `schema` | CSV parsing → validation → DB |
| `services` | `db`, `schema` | Business logic (CRUD, search, KiCad) |
| `api` | `services`, `db`, `config` | REST endpoints (JSON) |
| `ui` | `services`, `db`, `schema`, `config` | HTML pages (Jinja2) |
| `main` | all above | App factory, wiring, startup |

### Dual Import Routes

Both `api/routes_import.py` and `ui/routes_import.py` exist:
- **API version** (`/api/v1/import`): Returns JSON for programmatic use
- **UI version** (`/import`): Renders HTML form with upload and error display

Both internally call `import_engine.run_import()`.

### Value Sorting Algorithm

The smart value sorting in `search_service.py` handles:
- Metric prefixes: `p` (pico), `n` (nano), `u`/`µ` (micro), `m` (milli), `R` (unit), `K` (kilo), `M` (mega)
- R-notation: `4K7` → 4.7K, `3R3` → 3.3Ω
- Mixed formats: `"10K 1%"` extracts `10K` for sorting

### KiCad File Staging

Uploaded KiCad files go through a staging system:
1. Files uploaded via drag-drop are stored in `_staging/{session_id}/`
2. Properties can be edited before final save
3. On form submit, staged files are processed and moved to `kicad_libs/`
4. Unused staged files are auto-cleaned after 2 hours

### Cross-Platform Compatibility

All file paths use `pathlib.Path` for Windows/Linux/macOS compatibility:
- Forward slashes work on all platforms
- No hardcoded drive letters or backslashes
- Environment variable paths are resolved at runtime

---

## Contributing

Contributions are welcome! As this is an early-stage project, please reach out before 
making substantial changes:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/concept`)
3. Commit your changes (`git commit -m 'Add concept'`)
4. Push to the branch (`git push origin feature/concept`)
5. Open a Pull Request with a detailed description

## License

This project is licensed under the **GNU Affero General Public License v3.0 (AGPL-3.0)**.
See the [LICENSE](LICENSE) file for details.

### What this license means:

- ✅ **You can** freely use, modify, and distribute this software
- ✅ **You can** use this project for personal, educational, or internal purposes
- ✅ **You can** contribute improvements back to this project

- ⚠️ **You must** share any modifications you make if you distribute the software
- ⚠️ **You must** release the source code if you run a modified version on a server that others interact with
- ⚠️ **You must** keep all copyright notices intact

- ❌ **You cannot** incorporate this code into proprietary software without sharing your source code
- ❌ **You cannot** use this project in a commercial product without either complying with AGPL or obtaining a different license

### Commercial & Enterprise Use

Dual licensing options are available for commercial and enterprise users who require different terms. Please contact me through any of the channels listed in the [Contact](#contact) section to discuss commercial licensing arrangements.

## Contact

For questions or feedback:
- **Email:** [dvidmakesthings@gmail.com](mailto:dvidmakesthings@gmail.com)
- **GitHub:** [DvidMakesThings](https://github.com/DvidMakesThings)
