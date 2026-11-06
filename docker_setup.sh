#!/usr/bin/env bash
set -e

echo "===================================================="
echo " QSolutions Docker Automated Setup & Launch"
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

echo "[1/4] Building Docker container images..."
docker compose build

echo ""
echo "[2/4] Starting QSolutions Web Service container..."
docker compose up -d web-service

echo ""
echo "[3/4] Running automated verification tests inside Docker..."
docker compose run --rm tests

echo ""
echo "[4/4] Active Docker Containers:"
echo "===================================================="
docker ps --filter "name=qsolutions-web-service"
echo "===================================================="

echo ""
echo "SUCCESS: All services are configured and running!"
echo ""
echo "- Web Dashboard:  http://localhost:8000"
echo "- API Endpoints:  POST /upload, GET /get_video_url, GET /media/"
echo "- View Logs:      docker compose logs -f"
echo "- Stop Service:   docker compose down"
echo ""
