@echo off
@chcp 65001 >nul
setlocal EnableExtensions DisableDelayedExpansion

echo ====================================================
echo  Running Unit Tests for Web Service and API
echo ====================================================

where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python is not installed or not in PATH!
    pause
    exit /b 1
)

echo [1/3] Running Zoom Logic Tests (pytest)...
pytest test_zoom.py -v
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Zoom logic tests failed!
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo [2/3] Running Task 3 Impressum & DeepSeek Tests (unittest)...
python -m unittest test_task3.py -v
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Task 3 tests failed!
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo [3/3] Running Web Service Video Integration Tests...
python test_service.py -v

echo.
echo ====================================================
echo  Tests finished. Press any key to exit.
echo ====================================================
pause >nul
