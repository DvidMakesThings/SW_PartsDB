# PartsDB Quick Start

Get PartsDB running in 3 easy steps!

## Prerequisites

- Docker Desktop installed and running
- 4GB RAM available
- 10GB disk space

## Step 1: Run Deployment Script

### Windows (PowerShell)
```powershell
cd path\to\partsdb
.\deploy.ps1
```

### Linux/macOS (Terminal)
```bash
cd /path/to/partsdb
./deploy.sh
```

## Step 2: Access Application

Open your browser to:
- **Application**: http://localhost:5173

## Step 3: Create Admin User (Optional)

Run this command to create an admin account:

### Windows
```powershell
docker-compose -f partsdb\docker-compose.yml exec backend python manage.py createsuperuser
```

### Linux/macOS
```bash
docker-compose -f partsdb/docker-compose.yml exec backend python manage.py createsuperuser
```

Then access the admin panel at: http://localhost:8000/admin/

## That's It!

You can now:
- Browse components at http://localhost:5173
- Import CSV files via the Import page
- View inventory by location
- Edit components and manage inventory

## Useful Commands

### Stop Application
```bash
docker-compose -f partsdb/docker-compose.yml down
```

### View Logs
```bash
docker-compose -f partsdb/docker-compose.yml logs -f
```

### Restart
```bash
docker-compose -f partsdb/docker-compose.yml restart
```

For detailed documentation, see [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)
