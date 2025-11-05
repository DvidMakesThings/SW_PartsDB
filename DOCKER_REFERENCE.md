# Docker Reference for PartsDB

Quick reference for Docker commands used with PartsDB.

## Service Architecture

PartsDB consists of 5 Docker containers:

1. **PostgreSQL Database** (port 5432) - Stores all component and inventory data
2. **Redis Cache** (port 6379) - Message broker for Celery tasks
3. **Django Backend** (port 8000) - REST API server
4. **Celery Worker** - Background task processor (datasheets, imports)
5. **React Frontend** (port 5173) - User interface

## Common Commands

All commands assume you're in the project root directory.

### Starting Services

```bash
# Development mode
cd partsdb
docker-compose up -d

# Production mode
cd partsdb
docker-compose -f docker-compose.prod.yml up -d
```

### Stopping Services

```bash
# Stop all services
cd partsdb
docker-compose down

# Stop and remove volumes (⚠️ deletes data!)
cd partsdb
docker-compose down -v
```

### Viewing Logs

```bash
# All services
cd partsdb
docker-compose logs -f

# Specific service
cd partsdb
docker-compose logs -f backend
docker-compose logs -f frontend
docker-compose logs -f celery
docker-compose logs -f db

# Last 100 lines
cd partsdb
docker-compose logs --tail=100 backend
```

### Service Management

```bash
# Restart all services
cd partsdb
docker-compose restart

# Restart specific service
cd partsdb
docker-compose restart backend

# Check service status
cd partsdb
docker-compose ps

# View resource usage
cd partsdb
docker-compose stats
```

### Database Operations

```bash
# Run migrations
cd partsdb
docker-compose exec backend python manage.py migrate

# Create superuser
cd partsdb
docker-compose exec backend python manage.py createsuperuser

# Open database shell
cd partsdb
docker-compose exec backend python manage.py dbshell

# Django shell
cd partsdb
docker-compose exec backend python manage.py shell

# Backup database
cd partsdb
docker-compose exec -T db pg_dump -U postgres partsdb > backup_$(date +%Y%m%d).sql

# Restore database
cd partsdb
docker-compose exec -T db psql -U postgres partsdb < backup.sql
```

### File Operations

```bash
# Copy file into container
docker cp myfile.csv $(docker-compose ps -q backend):/app/myfile.csv

# Copy file from container
docker cp $(docker-compose ps -q backend):/app/media ./media_backup

# Access container filesystem
cd partsdb
docker-compose exec backend bash
docker-compose exec frontend sh
```

### Building and Updating

```bash
# Rebuild specific service
cd partsdb
docker-compose build backend

# Rebuild all services
cd partsdb
docker-compose build

# Rebuild without cache
cd partsdb
docker-compose build --no-cache

# Pull latest base images
cd partsdb
docker-compose pull
```

### Cleaning Up

```bash
# Remove stopped containers
docker container prune

# Remove unused images
docker image prune

# Remove unused volumes
docker volume prune

# Remove everything (⚠️ careful!)
docker system prune -a --volumes
```

## Development Workflows

### Making Code Changes

Backend changes (Python):
```bash
cd partsdb
docker-compose restart backend
```

Frontend changes (React):
- Changes are auto-reloaded (no restart needed in dev mode)
- For production build:
```bash
cd partsdb
docker-compose build frontend
docker-compose up -d frontend
```

### Running Tests

```bash
# Backend tests
cd partsdb
docker-compose exec backend pytest

# Specific test file
cd partsdb
docker-compose exec backend pytest tests/test_components.py

# With coverage
cd partsdb
docker-compose exec backend pytest --cov
```

### Import CSV Data

```bash
# Via management command
cd partsdb
docker-compose exec backend python manage.py import_csv /path/to/file.csv

# Copy file first, then import
docker cp mydata.csv $(docker-compose ps -q backend):/app/data.csv
cd partsdb
docker-compose exec backend python manage.py import_csv /app/data.csv
```

## Troubleshooting

### Port Conflicts

If ports are already in use, edit `docker-compose.yml`:

```yaml
services:
  frontend:
    ports:
      - "3000:5173"  # Change 3000 to any free port

  backend:
    ports:
      - "9000:8000"  # Change 9000 to any free port
```

### Container Won't Start

```bash
# View detailed logs
cd partsdb
docker-compose logs backend

# Check if port is in use
netstat -tulpn | grep 8000  # Linux
netstat -ano | findstr :8000  # Windows

# Remove and recreate
cd partsdb
docker-compose down
docker-compose up -d
```

### Database Connection Issues

```bash
# Restart database
cd partsdb
docker-compose restart db

# Check database logs
cd partsdb
docker-compose logs db

# Verify database is accessible
cd partsdb
docker-compose exec backend python manage.py dbshell
```

### Out of Disk Space

```bash
# Check Docker disk usage
docker system df

# Clean up unused resources
docker system prune -a

# Remove old images
docker image ls
docker image rm <image-id>
```

### Performance Issues

```bash
# Check resource usage
cd partsdb
docker stats

# Increase memory in Docker Desktop settings
# Or limit resources in docker-compose.yml:
services:
  backend:
    deploy:
      resources:
        limits:
          memory: 512M
```

## Environment Variables

Set in `docker-compose.yml` under each service's `environment:` section:

```yaml
environment:
  - DATABASE_URL=postgres://user:pass@db:5432/partsdb
  - REDIS_URL=redis://redis:6379/0
  - DEBUG=False
  - ALLOWED_HOSTS=localhost,127.0.0.1
  - SECRET_KEY=your-secret-key
```

## Networking

Services communicate via Docker network:

- Frontend → Backend: `http://backend:8000`
- Backend → Database: `postgresql://db:5432`
- Backend → Redis: `redis://redis:6379`

External access uses mapped ports:
- Frontend: `http://localhost:5173`
- Backend: `http://localhost:8000`

## Volumes

Data persistence:

```yaml
volumes:
  postgres_data:  # Database files
  ./backend/media:/app/media  # Uploaded files
```

To backup volumes:
```bash
docker run --rm -v postgres_data:/data -v $(pwd):/backup alpine tar czf /backup/db_backup.tar.gz /data
```

## Health Checks

Check if services are healthy:

```bash
# Backend health
curl http://localhost:8000/api/

# Database connection
cd partsdb
docker-compose exec backend python manage.py check --database default

# All services
cd partsdb
docker-compose ps
```

## Production Best Practices

1. Use `docker-compose.prod.yml` for production
2. Set strong passwords in environment variables
3. Use Docker secrets for sensitive data
4. Enable automatic restart: `restart: unless-stopped`
5. Monitor logs: `docker-compose logs -f`
6. Regular backups of database and media files
7. Update base images regularly
8. Limit container resources
9. Use reverse proxy (nginx/caddy) for HTTPS
10. Regular security updates

## Quick Reference Card

| Task | Command |
|------|---------|
| Start | `docker-compose up -d` |
| Stop | `docker-compose down` |
| Logs | `docker-compose logs -f` |
| Restart | `docker-compose restart` |
| Status | `docker-compose ps` |
| Shell | `docker-compose exec backend bash` |
| Migrate | `docker-compose exec backend python manage.py migrate` |
| Admin | `docker-compose exec backend python manage.py createsuperuser` |
| Backup | `docker-compose exec -T db pg_dump -U postgres partsdb > backup.sql` |
| Rebuild | `docker-compose build` |

For more help: `docker-compose --help` or `docker --help`
