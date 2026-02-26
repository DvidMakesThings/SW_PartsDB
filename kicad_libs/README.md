# DMTDB KiCad Libraries

This folder contains KiCad library files managed by DMTDB.

**Important:** KiCad's HTTP Library only supports symbols. Footprints and 3D models must be stored locally on each workstation. Use the **Download Libs** button in DMTDB to get all library files.

---

## Quick Start

### For DMTDB Users (Downloading Libraries)

1. Open DMTDB in your browser
2. Click the green **Download Libs** button in the navigation bar
3. Extract `DMTDB_KiCad_Libraries.zip` to a permanent location:
   - **Windows:** `C:\KiCad_Libs\DMTDB\`
   - **Linux:** `~/kicad_libs/dmtdb/`
4. Configure KiCad paths (see below)

### For Server Administrators

This folder on the server contains the source files:
- `symbols/` – Served via HTTP Library for real-time symbol browsing
- `footprints/` – Packaged in ZIP download for local use
- `3dmodels/` – Packaged in ZIP download for local use

---

## Folder Structure

**On the server:**
```
kicad_libs/
├── DMTDB.kicad_httplib        # HTTP Library configuration file
├── README.md                   # This file
├── symbols/                    # .kicad_sym files (HTTP browsable)
├── footprints/                 # .kicad_mod files (download for local use)
└── 3dmodels/                   # .step files (download for local use)
```

**On your workstation (after extracting the download):**
```
C:\KiCad_Libs\DMTDB\           # Or any location you prefer
├── symbols/                    # Symbol files (optional, for offline use)
├── footprints/                 # Footprint files (required)
├── 3dmodels/                   # 3D model files (required)
└── README.md                   # Setup instructions
```

---

## KiCad Configuration (Step-by-Step)

### Step 1: Download Libraries

1. Open DMTDB web interface
2. Click the green **Download Libs** button in the header
3. Save `DMTDB_KiCad_Libraries.zip`
4. Extract to a permanent location (you'll reference this path in KiCad)

**Recommended locations:**
| OS | Path |
|----|------|
| Windows | `C:\KiCad_Libs\DMTDB\` |
| Linux | `~/kicad_libs/dmtdb/` |
| macOS | `~/Documents/KiCad_Libs/DMTDB/` |

### Step 2: Configure Path Variables in KiCad

Go to **Preferences → Configure Paths** and add these entries:

| Name | Path (adjust to your extraction location) |
|------|-------------------------------------------|
| `DMTDB_ROOT` | `C:/KiCad_Libs/DMTDB/` |
| `DMTDB_SYM` | `${DMTDB_ROOT}/symbols/` |
| `DMTDB_FOOTPRINT` | `${DMTDB_ROOT}/footprints/` |
| `DMTDB_3D` | `${DMTDB_ROOT}/3dmodels/` |

> **Note:** Use forward slashes `/` in paths, even on Windows.

### Step 3: Add Footprint Library

Go to **Preferences → Manage Footprint Libraries → Global Libraries**:

1. Click **Add library** (+)
2. Set:
   - **Nickname:** `DMTDB`
   - **Library Path:** `${DMTDB_FOOTPRINT}`
   - **Library Type:** KiCad

### Step 4: Add Symbol Drawing Libraries

The HTTP library provides part metadata, but the actual symbol **drawings** come from `.kicad_sym` files. Add each symbol library to **Preferences → Manage Symbol Libraries → Global Libraries**:

| Nickname (must match exactly) | Library Path |
|-------------------------------|-------------|
| `DMTDB_PassiveComponents_Capacitors` | `${DMTDB_SYM}/DMTDB_PassiveComponents_Capacitors.kicad_sym` |
| `DMTDB_PassiveComponents_Resistors` | `${DMTDB_SYM}/DMTDB_PassiveComponents_Resistors.kicad_sym` |
| `DMTDB_PassiveComponents_Inductors` | `${DMTDB_SYM}/DMTDB_PassiveComponents_Inductors.kicad_sym` |

> **Critical:** The nicknames **must match exactly** as shown. Parts in the database reference symbols like `DMTDB_PassiveComponents_Resistors:R_Chip`. A mismatched nickname causes "symbol not found" errors.

### Step 5: Add HTTP Symbol Library

Go to **Preferences → Manage Symbol Libraries → Global Libraries**:

1. Click **Add library** (+)
2. Set:
   - **Nickname:** `DMTDB` *(must be exactly this name)*
   - **Library Path:** `${DMTDB_ROOT}/kicad_libs/DMTDB.kicad_httplib`
   - **Library Type:** KiCad (HTTP)

> **Critical:** The nickname **must be exactly `DMTDB`**. Parts in the database reference symbols using this library name (e.g., `DMTDB:R_Chip`). Using a different nickname will cause symbol lookup failures.

> **Important:** The `.kicad_httplib` file must be a **local file path**, not an HTTP URL. KiCad reads this local file, which contains the `root_url` pointing to the DMTDB server API. Edit the file to set the correct server address if needed.

### Step 6: Test the Setup

1. Open a schematic in KiCad
2. Press **A** to add a symbol
3. Expand **DMTDB** in the library browser
4. You should see categories like "01 Passive Components → 02 Resistors"
5. Select a part and verify the footprint resolves correctly

---

## Keeping Libraries in Sync

When new footprints or 3D models are added to DMTDB, update your local copy:

1. Click **Download Libs** in DMTDB
2. Extract the ZIP, overwriting existing files
3. KiCad will automatically use the updated files

**For Teams:** Consider setting up a shared network drive or using a sync script.

---

## File Naming Conventions

### Symbols

Symbol library files are organized by domain and family:

```
DMTDB_{DomainName}_{FamilyName}.kicad_sym
```

- **DomainName**: Domain name with spaces removed (e.g., `PassiveComponents`)
- **FamilyName**: Family name with spaces removed (e.g., `Capacitors`, `Resistors`)

Inside each library file, individual symbols are named descriptively:

| Component Type | Symbol Name Format | Example |
|----------------|-------------------|---------|
| Capacitor | `{Capacitance} {Voltage} {Package}` | `100nF 50V 0603` |
| Resistor | `{Resistance} {Tolerance} {Package}` | `10K 1% 0603` |
| Others | `{MPN}` | `BSS138LT1G` |

### Footprints

Footprint files use standard naming following KiCad conventions:

| Type | Format | Example |
|------|--------|---------|
| Chip capacitor | `C_{ImperialSize}_{MetricSize}Metric.kicad_mod` | `C_0603_1608Metric.kicad_mod` |
| Chip resistor | `R_{ImperialSize}_{MetricSize}Metric.kicad_mod` | `R_0805_2012Metric.kicad_mod` |
| SMD electrolytic | `CP_Elec_{DxH}.kicad_mod` | `CP_Elec_6.3x5.9.kicad_mod` |
| Disc capacitor | `C_Disc_D{D}mm_W{W}mm.kicad_mod` | `C_Disc_D10mm_W5.0mm.kicad_mod` |

### 3D Models

3D model files mirror footprint naming:

| Type | Format | Example |
|------|--------|---------|
| Chip component | `{Type}_{ImperialSize}_{MetricSize}Metric.step` | `R_0603_1608Metric.step` |
| Electrolytic | `CP_Elec_{DxH}.STEP` | `CP_Elec_6.3x5.9.STEP` |

---

## How KiCad Integration Works

### Symbol Browsing

When you add a symbol in KiCad:
1. KiCad queries `/kicad/v1/categories.json` for the category tree
2. You see a hierarchical view: `01 Passive Components → 01 Capacitors → ...`
3. When you expand a category, KiCad queries `/kicad/v1/parts.json?category_id=0101`
4. Parts appear with their MPN, Value, Description, and Quantity
5. Selecting a part loads its symbol and pre-fills properties

### Symbol Properties Mapping

When a symbol is placed, these properties are filled from DMTDB:

| Symbol Property | DMTDB Field |
|-----------------|-------------|
| `Reference` | Auto (R, C, U, etc.) |
| `Value` | Generated from component parameters or MPN |
| `Footprint` | KiCad footprint reference (format: `DMTDB:{name}`) |
| `Datasheet` | Datasheet URL or path |
| `Description` | Part description |
| `MFR` | Manufacturer |
| `MPN` | Manufacturer Part Number |
| `DMTUID` | Database unique ID |

### Footprint 3D Model Linking

Footprints reference 3D models using the `DMTDB_3D` environment variable:

```
(model "${DMTDB_3D}/C_0603_1608Metric.step"
  (offset (xyz 0 0 0))
  (scale (xyz 1 1 1))
  (rotate (xyz 0 0 0))
)
```

This allows the same footprint file to work whether accessed locally or via HTTP.

---

## Adding New Library Files

### Via Web Interface

1. Navigate to the part's edit page in DMTDB
2. Drag and drop `.kicad_sym`, `.kicad_mod`, or `.step` files onto the upload zone
3. For symbols, a modal opens to edit properties
4. Save the form – files are moved to their final locations

### Manually

1. **Symbols:** Add to `symbols/` directory. Name should follow `DMTDB_{Domain}_{Family}.kicad_sym` format, or add to an existing library file.

2. **Footprints:** Add `.kicad_mod` files directly to `footprints/`. Ensure 3D model paths use `${DMTDB_3D}/`.

3. **3D Models:** Add `.step` or `.wrl` files to `3dmodels/`.

### 3D Model Path Conversion

When uploading footprints through DMTDB, 3D model paths are automatically converted:

| Original Path | Converted Path |
|---------------|----------------|
| `${KICAD8_3DMODEL_DIR}/...` | `${DMTDB_3D}/filename.step` |
| `${KISYS3DMOD}/...` | `${DMTDB_3D}/filename.step` |
| Absolute paths | `${DMTDB_3D}/filename.step` |

---

## Network vs Local Setup

| Setup | Symbol Path | Footprint Path | 3D Path |
|-------|-------------|----------------|---------|
| **Local** | `/path/to/kicad_libs/symbols/` | `/path/to/kicad_libs/footprints/` | `/path/to/kicad_libs/3dmodels/` |
| **Network** | `http://server:5000/kicad_libs/symbols/` | `http://server:5000/kicad_libs/footprints/` | `http://server:5000/kicad_libs/3dmodels/` |

### Network Advantages
- Centralized library for entire team
- Parts database and library files stay in sync
- Changes propagate to all users automatically

### Local Advantages
- Works offline
- Faster file access (no network latency)
- Simple single-user setup

---

## Troubleshooting

### "Library not found" in KiCad

1. Verify DMTDB server is running
2. Check the URL in `DMTDB.kicad_httplib`
3. Test API access: `curl http://YOUR_SERVER:5000/kicad/v1/categories.json`

### 3D Models Not Showing

1. Check `DMTDB_3D` environment variable is set in KiCad
2. Verify path ends with `/` for URLs
3. Check file exists in `3dmodels/` folder

### Symbols Not Appearing in Browser

1. Ensure the part has a valid `kicad_symbol` field pointing to a symbol name
2. Check that the symbol library file exists in `symbols/`
3. Verify the HTTP library is added correctly

### Footprints Not Found

1. Check `DMTDB_FOOTPRINT` environment variable
2. Ensure footprint file exists in `footprints/`
3. Verify the part's `kicad_footprint` field matches the filename (without extension)

---

## API Endpoints for Libraries

DMTDB serves library files at these URLs:

| Endpoint | Description |
|----------|-------------|
| `GET /api/v1/libs/download` | **Download all libraries as ZIP** |
| `GET /kicad_libs/symbols/{filename}` | Download a symbol library file |
| `GET /kicad_libs/footprints/{filename}` | Download a footprint file |
| `GET /kicad_libs/3dmodels/{filename}` | Download a 3D model file |
| `GET /api/v1/libs` | JSON listing of all available library files |
| `GET /kicad/v1/categories.json` | Category tree for HTTP Library |
| `GET /kicad/v1/parts.json` | Parts list for HTTP Library |
