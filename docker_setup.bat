@echo off
setlocal

echo ====================================================
echo  QSolutions Multi-Container Docker Setup (Apache + PostgreSQL)
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

echo.
echo [1/3] Building and starting containers (Apache + PostgreSQL)...
docker compose up -d --build
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Docker compose failed to start!
    pause
    exit /b 1
)

echo.
echo [2/3] Running automated API and integration tests...
python test_service.py -v
if %ERRORLEVEL% neq 0 (
    echo [WARNING] Test execution encountered an issue.
)

echo.
echo [3/3] Active Docker Containers:
echo ====================================================
docker ps --filter "name=test_task_qsolutions"
echo ====================================================

echo.
echo SUCCESS: Apache web service and PostgreSQL database are running!
echo.
echo - Web Dashboard:  http://localhost:8000
echo - Web Server:     Apache 2.4 with mod_wsgi
echo - Database:       PostgreSQL 16 (database: videos, user: video_user)
echo - View Logs:      docker compose logs -f
echo - Stop Services:  docker compose down
echo.
echo Opening Dashboard in browser...
start http://localhost:8000
echo.
pause
