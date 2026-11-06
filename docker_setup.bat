@echo off
setlocal

echo ====================================================
echo  QSolutions Docker Automated Setup ^& Launch
echo ====================================================

where docker >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Docker is not installed or not in PATH!
    echo Please install Docker Desktop from https://www.docker.com/products/docker-desktop/
    pause
    exit /b 1
)

docker info >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Docker daemon is not running!
    echo Please start Docker Desktop and run this script again.
    pause
    exit /b 1
)

echo [1/4] Building Docker container images...
docker compose build
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Docker build failed!
    pause
    exit /b 1
)

echo.
echo [2/4] Starting QSolutions Web Service container...
docker compose up -d web-service
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to start container!
    pause
    exit /b 1
)

echo.
echo [3/4] Running automated verification tests inside Docker...
docker compose run --rm tests
if %ERRORLEVEL% neq 0 (
    echo [WARNING] Some tests encountered an issue.
)

echo.
echo [4/4] Active Docker Containers:
echo ====================================================
docker ps --filter "name=qsolutions-web-service"
echo ====================================================

echo.
echo SUCCESS: All services are configured and running!
echo.
echo - Web Dashboard:  http://localhost:8000
echo - API Endpoints:  POST /upload, GET /get_video_url, GET /media/
echo - View Logs:      docker compose logs -f
echo - Stop Service:   docker compose down
echo.
echo Opening Dashboard in browser...
start http://localhost:8000
echo.
pause
