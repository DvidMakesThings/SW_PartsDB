# PartsDB

A complete Electronic Parts Database management system for tracking components, datasheets, inventory and more.

## Features

- Comprehensive component database with categorization and search
- Automatic datasheet fetching and storage
- CSV import/export for component data
- Inventory management
- File management (datasheets, 3D models, photos)
- REST API for integration with other tools
- React-based frontend

## Quick Start (No Docker)

### Backend Setup

```bash
# Create a Python virtual environment
python -m venv .venv

# Activate the virtual environment
# On Windows:
.venv\Scripts\activate
# On Unix/MacOS:
# source .venv/bin/activate

# Install dependencies
pip install -r backend/requirements.txt

# Run migrations
cd backend
python manage.py migrate

# Start the backend server
python manage.py runserver
```

### Frontend Setup

```bash
# Navigate to frontend directory
cd frontend

# Install dependencies
npm i

# Start the development server
npm run dev
```

The backend will be available at http://localhost:8000/ and the frontend at http://localhost:5173/

## Docker Setup (Optional)

```bash
# Start all services
docker-compose up
```

## Environment Variables

The application uses the following environment variables (with defaults):

- `DATABASE_URL`: Database connection string (default: `sqlite:///backend/partsdb.sqlite3`)
- `MEDIA_ROOT`: Path for file storage (default: `backend/media`)
- `DATASHEET_FETCH_ENABLED`: Enable/disable datasheet fetching (default: `true`)
- `REDIS_URL`: Redis connection string for Celery (default: `redis://localhost:6379/0`, optional)

## File Storage Conventions

Files are stored under `MEDIA_ROOT` with deterministic paths:

- **Datasheets**: `Datasheets/<Manufacturer>/<Category_L1>/<MPN>.pdf`
- **3D models**: `3D/<Package>/<Variant>/<MPN>.step`
- **Photos**: `Photos/<MPN>/front.jpg`

## CSV Import

The system can import component data from CSV files. The importer maps column headers to model fields:

```
"MPN"->mpn, "Manufacturer"->manufacturer, "Value"->value, "Tolerance"->tolerance,
"Wattage"->wattage, "Voltage"->voltage, "Current"->current,
"Description"->description, "Datasheet"->url_datasheet,
"Package (LxW)"->package_l_mm/package_w_mm (parse "12.00mm x 12.00mm"),
"Height - after installation (max.)"->package_h_mm,
"Resistance"->extras.resistance, "Impedance"->extras.impedance
```

Components are deduplicated based on (manufacturer, mpn) pairs.

## Celery & Background Tasks

Datasheet fetching uses Celery for background processing:

- If Redis is available, fetching happens in the background
- If Redis is not available, fetching falls back to synchronous processing

## Future Enhancements

- PostgreSQL migration
- Authentication and permissions
- Barcode/QR support
- Bulk editing
- Advanced search/filtering
- Integration with additional ECAD tools

## Development

```bash
# Run tests
cd backend
pytest

# Create a superuser
python manage.py createsuperuser

# Make migrations after model changes
python manage.py makemigrations
```