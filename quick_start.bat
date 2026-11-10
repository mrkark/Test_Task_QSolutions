@echo off
setlocal

echo ====================================================
echo   QSolutions Project ^& Unit Tests Quick Launcher
echo ====================================================

where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python is not installed or not in PATH!
    echo Please install Python 3.9+ from https://python.org
    pause
    exit /b 1
)

:menu
echo.
echo Please select an action:
echo  [1] Start Web Service (Dashboard: http://127.0.0.1:8000)
echo  [2] Run Unit Tests (with full server responses)
echo  [3] Run Video Recorder (Task 1 local recording)
echo  [4] Run Full Pipeline (Recorder with Server Upload + Preview)
echo  [5] Record Video as Operator (Interactive F5 Zoom Test)
echo  [6] Setup & Run with Docker (Automated 1-click for Customer)
echo  [7] Exit
echo.
set /p choice="Enter choice [1-7] (default: 1): "

if "%choice%"=="" set choice=1
if "%choice%"=="1" goto start_server
if "%choice%"=="2" goto run_tests
if "%choice%"=="3" goto run_recorder
if "%choice%"=="4" goto run_pipeline
if "%choice%"=="5" goto record_interactive
if "%choice%"=="6" goto docker_setup
if "%choice%"=="7" goto exit_launcher

echo [!] Invalid selection, please enter 1 to 7.
goto menu

:start_server
echo.
echo [*] Starting Web Service at http://127.0.0.1:8000 ...
python web_service.py
goto end

:run_tests
echo.
echo [*] Running 10 Unit Tests with server response output...
python test_service.py -v
goto end

:run_recorder
echo.
echo [*] Running Playwright Video Recorder...
python capture_video.py
goto end

:run_pipeline
echo.
echo [*] Running Recorder with Server Upload and Chromium Preview...
python capture_video.py --server http://127.0.0.1:8000 --view-seconds 5
goto end

:record_interactive
echo.
echo [*] Launching Interactive Screen Recorder (Test F5 Zoom Live)...
call record_interactive.bat
goto end

:docker_setup
echo.
echo [*] Running automated Docker setup script...
call docker_setup.bat
goto end

:end
echo.
echo ====================================================
echo Action completed. Press any key to return to menu...
echo ====================================================
pause >nul
goto menu

:exit_launcher
echo Bye!
exit /b 0
