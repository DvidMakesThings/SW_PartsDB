# DMT Classification Integration Guide

## Overview

The PartsDB application has been restructured to use the DMT (Domain/Family/Class/Style) classification system for organizing electronic components. The system uses the DMT_Partslib.csv file as the primary data source and follows the hierarchical structure defined in dmt_schema.json and dmt_templates.json.

## DMT Classification System

The DMT classification uses a hierarchical code structure: **DMT-TTFFCCSSXXX**

- **TT**: Domain code (00-99) - Top-level category (e.g., 01 = Passive Components, 02 = Discrete Semiconductors)
- **FF**: Family code (00-99) - Component family within domain (e.g., 01 = Capacitors, 03 = MOSFETs)
- **CC**: Class code (00-99) - Specific class within family
- **SS**: Style code (00-99) - Style or variant
- **XXX**: Sequence number (001-999) - Unique identifier within classification

Example: `DMT-02030110001` = Discrete Semiconductors > MOSFETs > N-Channel > Standard > Sequence 001

## Database Schema Changes

### Component Model Updates

The Django Component model has been extended with the following DMT classification fields:

```python
dmtuid = models.CharField(max_length=20, unique=True, null=True, blank=True)
dmt_tt = models.CharField(max_length=2, null=True, blank=True)  # Domain
dmt_ff = models.CharField(max_length=2, null=True, blank=True)  # Family
dmt_cc = models.CharField(max_length=2, null=True, blank=True)  # Class
dmt_ss = models.CharField(max_length=2, null=True, blank=True)  # Style
dmt_xxx = models.CharField(max_length=3, null=True, blank=True) # Sequence
```

The DMTUID is automatically generated when all five classification codes are present.

### Supabase Tables (Optional)

For projects using Supabase, the following tables have been created:

- `dmt_domains` - Top-level domain classifications
- `dmt_families` - Component families within domains
- `dmt_classes` - Classes within families
- `dmt_styles` - Styles within families
- `components` - Main components table with DMT fields and JSONB field for dynamic attributes

## Importing DMT Data

### Using Django Management Command

To import the DMT_Partslib.csv file into your database:

```bash
cd partsdb/backend
python manage.py import_csv ../\_csv_renderer/DMT_Partslib.csv
```

Options:
- `--dry-run`: Test the import without making changes
- `--encoding=latin1`: Specify file encoding (default: utf-8)
- `--delimiter=,`: Specify CSV delimiter

Example with dry run:
```bash
python manage.py import_csv ../\_csv_renderer/DMT_Partslib.csv --dry-run
```

### CSV Field Mapping

The importer automatically maps the following CSV columns:

| CSV Column | Database Field | Description |
|------------|---------------|-------------|
| MPN | mpn | Manufacturer Part Number |
| Manufacturer | manufacturer | Manufacturer name |
| DMTUID | dmtuid | Full DMT classification code |
| TT | dmt_tt | Domain code |
| FF | dmt_ff | Family code |
| CC | dmt_cc | Class code |
| SS | dmt_ss | Style code |
| XXX | dmt_xxx | Sequence number |
| Value | value | Component value (e.g., "10uF", "100R") |
| Package / Case | package_name | Physical package type |
| Mounting Type | mounting_type | SMD/THT/etc |
| Operating Temperature | operating_temperature | Temperature range |
| RoHS | rohs | RoHS compliance |
| Datasheet | url_datasheet | Datasheet URL |

All other CSV columns are stored in the `extras` JSONB field for future reference.

## Frontend Updates

### Components List Page

The components list now displays the DMT UID alongside each component:

- DMT UID column shows the full classification code
- Styled with monospace font in a bordered badge
- Shows "—" for components without DMT classification

### Component Detail Page

The detail page now includes a dedicated DMT Classification section that displays:

- Full DMT UID
- Domain code (TT)
- Family code (FF)
- Class code (CC)
- Style code (SS)
- Sequence number (XXX)

This section only appears if the component has DMT classification data.

## Data Structure Files

### dmt_schema.json

Contains the complete DMT classification hierarchy:
- 29 domains (Passive Components, Semiconductors, ICs, etc.)
- Families within each domain
- Cross-cutting class codes (90-99) with special meanings
- Used to understand the classification structure

### dmt_templates.json

Maps component family codes to their specific field templates:
- Defines which fields are relevant for each component family
- Example: MOSFETs (0203) have fields like Vdss, Id, Rds(on), Vgs(th)
- Capacitors (0101) have fields like Capacitance, Voltage, Dielectric, ESR
- Used for dynamic field storage in the `extras` JSONB column

### DMT_Partslib.csv

The main data source containing:
- 134 real electronic components
- Complete DMT classification for each part
- Extensive metadata (specifications, datasheets, packages, etc.)
- MOSFETs, capacitors, resistors, inductors, ferrite beads, and more

## Usage Workflow

### 1. Start the Application

```bash
# Start the backend (Django)
cd partsdb/backend
python manage.py runserver

# Start the frontend (in another terminal)
cd partsdb/frontend
npm run dev
```

### 2. Import Components

```bash
cd partsdb/backend
python manage.py import_csv ../\_csv_renderer/DMT_Partslib.csv
```

### 3. Browse Components

Navigate to http://localhost:5173/components to see all imported components with their DMT classifications.

### 4. Search and Filter

Use the search bar to find components by:
- MPN (Manufacturer Part Number)
- Manufacturer name
- Description
- DMT UID

## API Endpoints

The Django REST API provides the following endpoints:

- `GET /api/components/` - List all components (paginated)
- `GET /api/components/{id}/` - Get single component details
- `POST /api/import/csv/` - Import components from CSV
- `GET /api/inventory/` - List inventory items

All endpoints return DMT classification fields in the response.

## Future Enhancements

Potential improvements to the DMT system:

1. **Hierarchical Navigation**: Browse components by Domain → Family → Class → Style
2. **DMT Lookup Views**: Dedicated pages for exploring the DMT hierarchy
3. **Auto-categorization**: Automatically assign categories based on DMT codes
4. **Field Templates**: Dynamically show/hide fields based on component family
5. **Validation**: Ensure DMT codes match the schema definitions
6. **Import Wizard**: Guided CSV import with DMT field mapping

## Troubleshooting

### Import Errors

If the CSV import fails:
1. Check the encoding (try `--encoding=latin1` or `--encoding=utf-8`)
2. Review error logs in `partsdb/backend/apps/inventory/import_errors/`
3. Use `--dry-run` to test without making changes

### Missing DMT Fields

If DMT fields don't appear:
1. Verify the CSV has TT, FF, CC, SS, XXX columns
2. Check that the importer field mapping includes DMT fields
3. Ensure the database migration has been applied

### Frontend Not Showing DMT Data

1. Check browser console for API errors
2. Verify backend is returning DMT fields in API response
3. Clear browser cache and refresh

## Migration Notes

To apply the database schema changes for DMT fields, create and run a Django migration:

```bash
cd partsdb/backend
python manage.py makemigrations inventory --name add_dmt_classification
python manage.py migrate
```

The migration will add the new DMT fields to the existing Component model without losing data.

## Summary

The PartsDB application now fully supports the DMT classification system:

✅ Database schema updated with DMT fields
✅ CSV importer handles DMT columns
✅ Frontend displays DMT classifications
✅ API returns DMT data
✅ Components organized using real DMT_Partslib.csv data
✅ Dummy data eliminated - all data comes from real parts library

The system is now ready to manage electronic components using the universal DMT classification standard.
