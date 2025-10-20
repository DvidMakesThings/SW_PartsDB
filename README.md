# PartsDB - Electronic Components Inventory System

PartsDB is a comprehensive inventory management system for electronic components, supporting component cataloging, inventory tracking, datasheet management, and CSV imports.

## Quick Start (No Docker)

### Windows / PowerShell

```powershell
# Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\activate

# Install dependencies
pip install -r backend/requirements.txt

# Initialize database and run server
cd backend && python manage.py migrate && python manage.py runserver 0.0.0.0:8000
```

### Linux / macOS

```bash
# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r backend/requirements.txt

# Initialize database and run server
cd backend && python manage.py migrate && python manage.py runserver 0.0.0.0:8000
```

### Frontend Setup (In Another Terminal)

```bash
cd frontend
npm i
npm run dev
```

Default URLs:
- Backend: http://127.0.0.1:8000
- Frontend: http://127.0.0.1:5173
- Admin interface: http://127.0.0.1:8000/admin
- API documentation: http://127.0.0.1:8000/api/schema/swagger/

## Docker Setup (Optional)

```bash
# Start all services
docker compose up -d

# First-time setup: Run migrations
docker compose exec web python manage.py migrate

# Create admin user
docker compose exec web python manage.py createsuperuser
```

## Environment Variables

Create a `.env` file at the project root with the following variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite:///backend/partsdb.sqlite3` | Database connection string |
| `MEDIA_ROOT` | `backend/media` | File storage root directory |
| `DATASHEET_FETCH_ENABLED` | `true` | Enable/disable datasheet fetching |
| `REDIS_URL` | _(optional)_ | Redis URL for Celery tasks (if empty, datasheet fetch runs synchronously) |
| `DJANGO_DEBUG` | `true` | Enable debug mode |
| `DJANGO_SECRET_KEY` | `change-me` | Secret key for Django |
| `VITE_API_BASE` | `http://127.0.0.1:8000` | API base URL for frontend |

## File Storage Conventions

Files are stored under `MEDIA_ROOT` with the following structure:

- **Datasheets**: `Datasheets/<Manufacturer>/<Category_L1>/<MPN>.pdf`
- **3D Models**: `3D/<Package>/<Variant>/<MPN>.step`
- **Photos**: `Photos/<MPN>/front.jpg`

## CSV Import

### Using the Command Line

```bash
# Dry run (shows changes without applying them)
python backend/manage.py import_csv backend/tests/sample_components.csv --dry-run

# Actual import
python backend/manage.py import_csv backend/tests/sample_components.csv
```

### Using the API

```
POST /api/import/csv
```
- Multipart form data with:
  - `file`: CSV file to import
  - `dry_run`: `true` or `false`

### Header Mapping

The importer accepts various headers and maps them to model fields:

- `MPN` → `mpn` (normalized to uppercase)
- `Manufacturer` → `manufacturer`
- `Value` → `value`
- `Tolerance` → `tolerance`
- `Wattage` → `wattage`
- `Voltage` → `voltage`
- `Current` → `current`
- `Description` → `description`
- `Datasheet` → `url_datasheet`
- `Package (LxW)` → parses dimensions like "12.00mm x 12.00mm" into `package_l_mm` and `package_w_mm`
- `Height - after installation (max.)` → `package_h_mm`
- Other fields like `Resistance`, `Impedance` → stored in `extras` JSON field

Components are de-duplicated based on normalized manufacturer and MPN. Existing data is preserved when fields already contain values.

### Error Handling

Rows with errors are logged to: `backend/apps/inventory/import_errors/YYYYMMDD_HHMM.csv`

## Datasheet Fetching

### Fetching Individual Datasheets

```
POST /api/components/{id}/fetch_datasheet/
```

### Batch Fetching Missing Datasheets

```
POST /api/components/fetch_missing_datasheets/
```

- Datasheets are only accepted if content-type is `application/pdf`
- Files are stored with SHA-256 deduplication
- If `REDIS_URL` is not set, fetching runs synchronously instead of using Celery

## API Documentation

- **Swagger UI**: `/api/schema/swagger/`
- **OpenAPI Schema**: `/api/schema/`
- **Health Check**: `/api/health` (returns `{"ok": true}`)

## Admin Interface

Access the Django admin at `/admin`

To create a superuser:
```bash
python backend/manage.py createsuperuser
```

## Testing & Quality

### Running Tests

```bash
cd backend
pytest -q
```

### Linting and Formatting

```bash
# Linting
ruff check backend

# Formatting
ruff format backend
```

### Acceptance Tests

✅ `python -m venv .venv && pip install -r backend/requirements.txt && cd backend && python manage.py migrate && python manage.py runserver` starts without error.  
✅ `curl http://localhost:8000/api/health` returns `{"ok":true}`.  
✅ `python backend/manage.py import_csv backend/tests/sample_components.csv --dry-run` prints a summary.  
✅ `python backend/manage.py import_csv backend/tests/sample_components.csv` creates rows.  
✅ `POST /api/components/?search=SN65HVD11` returns the component.  
✅ `POST /api/components/{id}/fetch_datasheet/` stores a PDF under `backend/media/Datasheets/...`.  
✅ Frontend `npm i && npm run dev` starts and lists components without errors.  

## Future Roadmap

- PostgreSQL migration (using `DATABASE_URL=postgres://...`)
- Barcode/QR support for inventory items
- Bulk edits & CSV export functionality
- EAGLE ULP integration using `/api/stock_check` endpoint
- CI/CD with GitHub Actions
- Enhanced Redis/Celery configuration for production

## License
### Software Components
This project's software is licensed under the **GNU Affero General Public License v3.0 (AGPL-3.0)**.
See the [Software License](LICENSE-AGPL) file for details.

#### What AGPL-3.0 means:

- ✅ **You can** freely use, modify, and distribute this software
- ✅ **You can** use this project for personal, educational, or internal purposes
- ✅ **You can** contribute improvements back to this project

- ⚠️ **You must** share any modifications you make if you distribute the software
- ⚠️ **You must** release the source code if you run a modified version on a server that others interact with
- ⚠️ **You must** keep all copyright notices intact

- ❌ **You cannot** incorporate this code into proprietary software without sharing your source code
- ❌ **You cannot** use this project in a commercial product without either complying with AGPL or obtaining a different license

### Commercial & Enterprise Use

Commercial use of this project is prohibited without obtaining a separate commercial license. If you are interested in:

- Manufacturing and selling products based on these designs
- Incorporating these designs into commercial products
- Any other commercial applications

Please contact me through any of the channels listed in the [Contact](#contact) section to discuss commercial licensing arrangements. Commercial licenses are available with reasonable terms to support ongoing development.

## Contact

For questions or feedback:
- **Email:** [dvidmakesthings@gmail.com](mailto:dvidmakesthings@gmail.com)
- **GitHub:** [DvidMakesThings](https://github.com/DvidMakesThings)

## Contributing

Contributions are welcome! As this is an early-stage project, please reach out before 
making substantial changes:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/concept`)
3. Commit your changes (`git commit -m 'Add concept'`)
4. Push to the branch (`git push origin feature/concept`)
5. Open a Pull Request with a detailed description