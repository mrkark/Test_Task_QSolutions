@echo off
setlocal enabledelayedexpansion

echo ====================================================
echo  QSolutions Browser Automation ^& Web Service
echo ====================================================

where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python is not installed or not in PATH!
    echo Please install Python 3.9+ from https://python.org
    pause
    exit /b 1
)

echo [1/2] Checking and installing Python dependencies...
python -m pip install -r requirements.txt >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo Failed installing requirements. Retrying with verbose output...
    python -m pip install -r requirements.txt
)

echo [2/2] Ensuring Playwright Chromium browser is installed...
python -m playwright install chromium

if not "%~1"=="" (
    echo [RUN] Executing capture_video.py with arguments: %*
    python capture_video.py %*
    goto end
)

:menu
echo.
echo ====================================================
echo  Select Run Mode:
echo ====================================================
echo  [1] Full Pipeline (Auto-start server + record + upload + preview)
echo  [2] Web Service Dashboard (Start server at http://127.0.0.1:8000)
echo  [3] Video Recorder Only (Task 1 local recording)
echo  [4] Run Unit Tests (Task 2 API verification with server responses)
echo  [5] Exit
echo ====================================================
set /p choice="Enter option [1-5] (default: 1): "

if "%choice%"=="" set choice=1
if "%choice%"=="1" goto run_full
if "%choice%"=="2" goto run_server
if "%choice%"=="3" goto run_recorder
if "%choice%"=="4" goto run_tests
if "%choice%"=="5" goto end
echo Invalid selection. Please choose 1, 2, 3, 4, or 5.
goto menu

:run_full
echo.
echo [INFO] Running full pipeline with automatic server upload and preview...
python capture_video.py --auto-server --view-seconds 5
goto end

:run_server
echo.
echo [INFO] Starting web service dashboard on http://127.0.0.1:8000 ...
python web_service.py
goto end

:run_recorder
echo.
echo [INFO] Running video recorder only...
python capture_video.py
goto end

:run_tests
echo.
echo [INFO] Running unit tests with server response logs...
python test_service.py -v
goto end

:end
echo.
echo ====================================================
echo Execution finished.
echo ====================================================
pause
