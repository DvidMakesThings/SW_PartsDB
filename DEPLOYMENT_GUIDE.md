# PartsDB Deployment Guide

This guide explains how to deploy PartsDB using Docker containers.

## Prerequisites

### Windows
- Windows 10/11 with WSL2 enabled
- Docker Desktop for Windows (https://www.docker.com/products/docker-desktop)
- PowerShell 5.1 or later

### Linux/macOS
- Docker Engine (https://docs.docker.com/engine/install/)
- Docker Compose (https://docs.docker.com/compose/install/)
- Bash shell

## Quick Start

### Windows Deployment

1. Open PowerShell as Administrator
2. Navigate to the project root directory:
   ```powershell
   cd path\to\partsdb
   ```
3. Run the deployment script:
   ```powershell
   .\deploy.ps1
   ```

### Linux/macOS Deployment

1. Open Terminal
2. Navigate to the project root directory:
   ```bash
   cd /path/to/partsdb
   ```
3. Run the deployment script:
   ```bash
   ./deploy.sh
   ```

## What the Deployment Script Does

The deployment script automatically:

1. ✓ Checks if Docker is installed and running
2. ✓ Builds Docker images for all services:
   - PostgreSQL database
   - Redis cache
   - Django backend API
   - Celery worker
   - React frontend
3. ✓ Stops any existing containers
4. ✓ Starts all containers in detached mode
5. ✓ Runs database migrations
6. ✓ Displays service status

## Accessing the Application

After successful deployment:

- **Frontend**: http://localhost:5173
- **Backend API**: http://localhost:8000
- **API Documentation**: http://localhost:8000/api/schema/swagger-ui/
- **Admin Panel**: http://localhost:8000/admin/

## Post-Deployment Steps

### 1. Create Admin User

To access the Django admin panel:

**Windows:**
```powershell
docker-compose -f partsdb\docker-compose.yml exec backend python manage.py createsuperuser
```

**Linux/macOS:**
```bash
docker-compose -f partsdb/docker-compose.yml exec backend python manage.py createsuperuser
```

Follow the prompts to create your admin account.

### 2. Import Initial Data (Optional)

If you have a CSV file with component data:

1. Navigate to http://localhost:5173
2. Go to "Import CSV" page
3. Upload your CSV file

Or use the backend import command:

**Windows:**
```powershell
docker-compose -f partsdb\docker-compose.yml exec backend python manage.py import_csv path/to/your/file.csv
```

**Linux/macOS:**
```bash
docker-compose -f partsdb/docker-compose.yml exec backend python manage.py import_csv path/to/your/file.csv
```

## Useful Docker Commands

### View Logs

**All services:**
```bash
docker-compose -f partsdb/docker-compose.yml logs -f
```

**Specific service:**
```bash
docker-compose -f partsdb/docker-compose.yml logs -f backend
docker-compose -f partsdb/docker-compose.yml logs -f frontend
```

### Stop Application

```bash
docker-compose -f partsdb/docker-compose.yml down
```

### Stop and Remove All Data (including database)

⚠️ **WARNING**: This will delete all data!

```bash
docker-compose -f partsdb/docker-compose.yml down -v
```

### Restart Services

```bash
docker-compose -f partsdb/docker-compose.yml restart
```

### Restart Specific Service

```bash
docker-compose -f partsdb/docker-compose.yml restart backend
docker-compose -f partsdb/docker-compose.yml restart frontend
```

### Check Service Status

```bash
docker-compose -f partsdb/docker-compose.yml ps
```

### Access Container Shell

**Backend:**
```bash
docker-compose -f partsdb/docker-compose.yml exec backend bash
```

**Frontend:**
```bash
docker-compose -f partsdb/docker-compose.yml exec frontend sh
```

## Production Deployment

For production environments, use the production docker-compose file:

```bash
docker-compose -f partsdb/docker-compose.prod.yml up -d
```

The production configuration includes:

- Gunicorn WSGI server for Django (4 workers)
- Nginx web server for frontend
- Optimized build with static assets
- Automatic container restart
- Proper caching headers

**Production URL**: http://localhost (port 80)

### Production Environment Variables

Before deploying to production, update these settings in `docker-compose.prod.yml`:

1. Change PostgreSQL credentials:
   ```yaml
   POSTGRES_PASSWORD=your_secure_password
   ```

2. Set Django secret key:
   ```yaml
   SECRET_KEY=your_secure_secret_key
   ```

3. Configure allowed hosts:
   ```yaml
   ALLOWED_HOSTS=your-domain.com,localhost
   ```

## Troubleshooting

### Port Already in Use

If you get "port already in use" errors:

1. Check what's using the port:
   ```bash
   # Windows
   netstat -ano | findstr :5173
   netstat -ano | findstr :8000

   # Linux/macOS
   lsof -i :5173
   lsof -i :8000
   ```

2. Stop the conflicting service or change ports in `docker-compose.yml`

### Database Connection Errors

If the backend can't connect to the database:

1. Ensure PostgreSQL container is running:
   ```bash
   docker-compose -f partsdb/docker-compose.yml ps db
   ```

2. Check database logs:
   ```bash
   docker-compose -f partsdb/docker-compose.yml logs db
   ```

3. Restart the database:
   ```bash
   docker-compose -f partsdb/docker-compose.yml restart db
   ```

### Frontend Can't Reach Backend

1. Check if backend is running:
   ```bash
   curl http://localhost:8000/api/
   ```

2. Verify frontend proxy configuration in `vite.config.ts`

3. Restart both services:
   ```bash
   docker-compose -f partsdb/docker-compose.yml restart backend frontend
   ```

### Build Failures

If Docker build fails:

1. Clear Docker build cache:
   ```bash
   docker system prune -a
   ```

2. Rebuild from scratch:
   ```bash
   docker-compose -f partsdb/docker-compose.yml build --no-cache
   ```

### Out of Memory

If containers are killed due to memory:

1. Increase Docker memory limit in Docker Desktop settings
2. Reduce number of Celery workers in `docker-compose.yml`

## Backup and Restore

### Backup Database

```bash
docker-compose -f partsdb/docker-compose.yml exec -T db pg_dump -U postgres partsdb > backup.sql
```

### Restore Database

```bash
docker-compose -f partsdb/docker-compose.yml exec -T db psql -U postgres partsdb < backup.sql
```

### Backup Media Files

```bash
docker cp $(docker-compose -f partsdb/docker-compose.yml ps -q backend):/app/media ./media_backup
```

## Updating the Application

To update PartsDB to a new version:

1. Pull latest changes:
   ```bash
   git pull origin main
   ```

2. Rebuild containers:
   ```bash
   docker-compose -f partsdb/docker-compose.yml build
   ```

3. Stop and start services:
   ```bash
   docker-compose -f partsdb/docker-compose.yml down
   docker-compose -f partsdb/docker-compose.yml up -d
   ```

4. Run migrations:
   ```bash
   docker-compose -f partsdb/docker-compose.yml exec backend python manage.py migrate
   ```

## Performance Optimization

### Database Optimization

1. Create indexes for frequently queried fields (already done in models)
2. Increase PostgreSQL shared_buffers in `docker-compose.yml`:
   ```yaml
   command: postgres -c shared_buffers=256MB -c max_connections=200
   ```

### Frontend Optimization

The production build automatically:
- Minifies JavaScript and CSS
- Optimizes images
- Enables gzip compression
- Sets proper cache headers

### Backend Optimization

Adjust Gunicorn workers based on CPU cores:
```yaml
command: gunicorn partsdb.wsgi:application --bind 0.0.0.0:8000 --workers 8
```

Rule of thumb: `(2 x CPU cores) + 1`

## Security Considerations

For production deployment:

1. ✓ Use strong passwords for database
2. ✓ Set DEBUG=False
3. ✓ Configure ALLOWED_HOSTS properly
4. ✓ Use environment variables for secrets
5. ✓ Enable HTTPS with reverse proxy (nginx/caddy)
6. ✓ Regular security updates
7. ✓ Implement proper authentication
8. ✓ Regular backups

## Support

For issues or questions:
- Check logs: `docker-compose logs -f`
- Review error messages in the browser console
- Verify all containers are running: `docker-compose ps`
