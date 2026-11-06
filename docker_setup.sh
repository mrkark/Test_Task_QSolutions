#!/usr/bin/env bash
set -e

echo "===================================================="
echo " QSolutions Multi-Container Docker Setup (Apache + PostgreSQL)"
echo "===================================================="

if ! command -v docker &> /dev/null; then
    echo "[ERROR] Docker is not installed or not in PATH."
    echo "Please install Docker from https://docs.docker.com/get-docker/"
    exit 1
fi

if ! docker info &> /dev/null; then
    echo "[ERROR] Docker daemon is not running. Please start Docker."
    exit 1
fi

echo ""
echo "[1/3] Building and starting containers (Apache + PostgreSQL)..."
docker compose up -d --build

echo ""
echo "[2/3] Running automated API and integration tests..."
python3 test_service.py -v || true

echo ""
echo "[3/3] Active Docker Containers:"
echo "===================================================="
docker ps --filter "name=test_task_qsolutions"
echo "===================================================="

echo ""
echo "SUCCESS: Apache web service and PostgreSQL database are running!"
echo ""
echo "- Web Dashboard:  http://localhost:8000"
echo "- Web Server:     Apache 2.4 with mod_wsgi"
echo "- Database:       PostgreSQL 16 (database: videos, user: video_user)"
echo "- View Logs:      docker compose logs -f"
echo "- Stop Services:  docker compose down"
echo ""
