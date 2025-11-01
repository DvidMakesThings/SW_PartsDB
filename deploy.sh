#!/bin/bash
# PartsDB Deployment Script for Linux/macOS
# This script builds Docker images and starts the PartsDB application

echo "========================================"
echo "  PartsDB Deployment Script (Linux)"
echo "========================================"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
GRAY='\033[0;37m'
NC='\033[0m' # No Color

# Check if Docker is installed
echo -e "${YELLOW}Checking Docker installation...${NC}"
if command -v docker &> /dev/null; then
    DOCKER_VERSION=$(docker --version)
    echo -e "${GREEN}✓ Docker found: $DOCKER_VERSION${NC}"
else
    echo -e "${RED}✗ Docker is not installed${NC}"
    echo -e "${RED}Please install Docker from: https://docs.docker.com/get-docker/${NC}"
    exit 1
fi

# Check if Docker Compose is installed
echo -e "${YELLOW}Checking Docker Compose installation...${NC}"
if command -v docker-compose &> /dev/null; then
    COMPOSE_VERSION=$(docker-compose --version)
    echo -e "${GREEN}✓ Docker Compose found: $COMPOSE_VERSION${NC}"
else
    echo -e "${RED}✗ Docker Compose is not installed${NC}"
    echo -e "${RED}Please install Docker Compose from: https://docs.docker.com/compose/install/${NC}"
    exit 1
fi

# Check if Docker is running
echo -e "${YELLOW}Checking if Docker is running...${NC}"
if docker ps &> /dev/null; then
    echo -e "${GREEN}✓ Docker is running${NC}"
else
    echo -e "${RED}✗ Docker is not running${NC}"
    echo -e "${RED}Please start Docker and try again${NC}"
    exit 1
fi

# Navigate to partsdb directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR/partsdb"

echo ""
echo -e "${YELLOW}Building Docker images...${NC}"
echo -e "${GRAY}This may take several minutes on first run...${NC}"
echo ""

# Build images using docker-compose
docker-compose build

echo ""
echo -e "${GREEN}✓ Docker images built successfully${NC}"
echo ""

# Stop any existing containers
echo -e "${YELLOW}Stopping any existing containers...${NC}"
docker-compose down

# Start the application
echo ""
echo -e "${YELLOW}Starting PartsDB application...${NC}"
docker-compose up -d

# Wait for services to initialize
echo ""
echo -e "${YELLOW}Waiting for services to initialize...${NC}"
sleep 5

# Run database migrations
echo -e "${YELLOW}Running database migrations...${NC}"
docker-compose exec -T backend python manage.py migrate || {
    echo -e "${YELLOW}⚠ Warning: Database migrations may have failed${NC}"
    echo -e "${YELLOW}You may need to run migrations manually:${NC}"
    echo -e "${GRAY}  docker-compose exec backend python manage.py migrate${NC}"
}

# Check service status
echo ""
echo -e "${YELLOW}Checking service status...${NC}"
echo ""
docker-compose ps

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  PartsDB is now running!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${CYAN}Access the application at:${NC}"
echo -e "  Frontend: ${NC}http://localhost:5173"
echo -e "  Backend:  ${NC}http://localhost:8000"
echo -e "  API Docs: ${NC}http://localhost:8000/api/schema/swagger-ui/"
echo ""
echo -e "${CYAN}Useful commands:${NC}"
echo -e "${GRAY}  View logs:         docker-compose logs -f${NC}"
echo -e "${GRAY}  Stop application:  docker-compose down${NC}"
echo -e "${GRAY}  Restart:           docker-compose restart${NC}"
echo -e "${GRAY}  Create admin:      docker-compose exec backend python manage.py createsuperuser${NC}"
echo ""
echo -e "${YELLOW}Press Ctrl+C to exit (containers will continue running)${NC}"
echo ""
